"""Holds a trader's call to a tool that needs the user's permission, and asks for it.

The tools listed in [approvals] tools are never run straight away when a trader or one of its subagents calls them. The call is saved as a permission request that lapses after [approvals] expiry_minutes, and the model is told to end its turn. If the user allows it, the harness runs exactly that call; the model never gets a way around it. A standing "Always allow" grant lets the call through at once.

The user's own actions, such as the Flatten button on the Traders page, do not pass through this gate.

Typical usage example:

  gate = PermissionGate(['flatten_trader'], 5, store, grants, event_bus)
  if gate.needs_permission('main', call.name):
      result = gate.hold('main', call)
"""

import datetime
from collections.abc import Collection

from trading_agent.agent import messages
from trading_agent.requests import permission_grants as permission_grants_module
from trading_agent.requests import user_request as user_request_module
from trading_agent.requests import (
    user_request_store as user_request_store_module,
)
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.tools import tool as tool_module

_INDIA = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


class PermissionGate:
    """Decides which calls need permission, and turns them into permission requests."""

    def __init__(
        self,
        tool_names: Collection[str],
        expiry_minutes: int,
        store: user_request_store_module.UserRequestStore,
        grants: permission_grants_module.PermissionGrants,
        event_bus: event_bus_module.EventBus,
    ):
        """Creates the gate.

        Args:
            tool_names (Collection[str]): The tools that need permission.
            expiry_minutes (int): How long a request stays open.
            store (user_request_store_module.UserRequestStore): Where requests are saved.
            grants (permission_grants_module.PermissionGrants): The standing permissions.
            event_bus (event_bus_module.EventBus): Where requests are published for the web page and Telegram.
        """
        self._tool_names = set(tool_names)
        self._expiry_minutes = expiry_minutes
        self._store = store
        self._grants = grants
        self._event_bus = event_bus

    def needs_permission(self, trader_name: str, tool_name: str) -> bool:
        """Says whether a call must wait for the user.

        Args:
            trader_name (str): The trader calling.
            tool_name (str): The tool called.

        Returns:
            bool: True when the tool is covered and the trader has no standing permission for it.
        """
        if tool_name not in self._tool_names:
            return False
        return not self._grants.allows(trader_name, tool_name)

    def hold(
        self, trader_name: str, call: messages.ToolCall
    ) -> tool_module.ToolResult:
        """Saves and publishes a permission request for a call, instead of running it.

        Args:
            trader_name (str): The trader calling.
            call (messages.ToolCall): The call held.

        Returns:
            tool_module.ToolResult: What the model is told: the request, when it lapses, and to end the turn.
        """
        expires_at = datetime.datetime.now(datetime.UTC) + datetime.timedelta(
            minutes=self._expiry_minutes
        )
        request = user_request_module.UserRequest.new(
            trader_name,
            user_request_module.PERMISSION,
            {
                'tool_name': call.name,
                'arguments': call.arguments,
                'call_id': call.call_id,
            },
            expires_at,
        )
        self._store.save(request)
        self._event_bus.publish(
            event_module.Event.now(
                event_module.EventKind.USER_REQUEST,
                trader_name,
                request.to_json_dictionary(),
            )
        )
        lapse = expires_at.astimezone(_INDIA).strftime('%H:%M')
        return tool_module.ToolResult.success(
            f"{call.name} needs the user's permission, so it was not run. Request {request.request_id} was sent to them and lapses at {lapse} India time. End this turn now; do not retry {call.name} or reach the same result another way. If they allow it, the harness runs exactly this call and tells you the result in a new message."
        )
