"""Records the user's response to a trader's request and hands it to the trader as a new message.

The web page and Telegram both answer through this class, so a request answered in one place shows as answered in the other.

Typical usage example:

  responder = UserRequestResponder(store, event_bus, traders)
  responder.answer_question(request_id, [{'selected': ['Wait'], 'other': ''}], 'web')
"""

import dataclasses
import datetime
from collections.abc import Mapping, Sequence
from typing import Any

from trading_agent.agent import messages
from trading_agent.requests import permission_grants as permission_grants_module
from trading_agent.requests import (
    permission_response as permission_response_module,
)
from trading_agent.requests import plan_response as plan_response_module
from trading_agent.requests import question_response as question_response_module
from trading_agent.requests import user_request as user_request_module
from trading_agent.requests import (
    user_request_store as user_request_store_module,
)
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trader_runtime
from trading_agent.runtime import trigger as trigger_module
from trading_agent.tools import tool_registry as tool_registry_module


class UserRequestResponder:
    """Answers questions, decides plans and permissions, and dismisses requests on the user's behalf."""

    def __init__(
        self,
        store: user_request_store_module.UserRequestStore,
        event_bus: event_bus_module.EventBus,
        traders: Mapping[str, trader_runtime.TraderRuntime],
        tool_registries: Mapping[str, tool_registry_module.ToolRegistry]
        | None = None,
        grants: permission_grants_module.PermissionGrants | None = None,
    ):
        """Creates the responder.

        Args:
            store (user_request_store_module.UserRequestStore): Where requests are kept.
            event_bus (event_bus_module.EventBus): Where each response is published.
            traders (Mapping[str, trader_runtime.TraderRuntime]): The running traders, keyed by name, which receive the responses.
            tool_registries (Mapping[str, tool_registry_module.ToolRegistry] | None): Each trader's tools, which run a call the user allows; None when permissions are not used.
            grants (permission_grants_module.PermissionGrants | None): Where "Always allow" is saved; None when permissions are not used.
        """
        self._store = store
        self._event_bus = event_bus
        self._traders = traders
        self._tool_registries = tool_registries or {}
        self._grants = grants

    def answer_question(
        self,
        request_id: str,
        answers: Sequence[dict[str, Any]],
        via: str,
    ) -> user_request_module.UserRequest:
        """Records the answers to a question request and tells the trader.

        Args:
            request_id (str): The request.
            answers (Sequence[dict[str, Any]]): One {"selected": [labels], "other": text} per question.
            via (str): "web", "terminal" or "telegram".

        Returns:
            user_request_module.UserRequest: The answered request.

        Raises:
            user_request_store_module.UserRequestError: The request does not exist or is no longer pending.
            ValueError: The request is not a question, or the answers do not fit it.
        """
        request = self._store.pending_request(request_id)
        if request.kind != user_request_module.QUESTION:
            raise ValueError(
                f'Request {request_id} is a {request.kind}, not a question'
            )
        response = question_response_module.QuestionResponse(request, answers)
        response.check()
        return self._finish(
            request,
            user_request_module.ANSWERED,
            response.stored(),
            response.message(),
            via,
        )

    def decide_plan(
        self,
        request_id: str,
        decision: str,
        feedback: str,
        via: str,
    ) -> user_request_module.UserRequest:
        """Records the decision on a plan and tells the trader.

        Args:
            request_id (str): The request.
            decision (str): "approve" or "revise".
            feedback (str): What should change, or a note with an approval.
            via (str): "web", "terminal" or "telegram".

        Returns:
            user_request_module.UserRequest: The decided request.

        Raises:
            user_request_store_module.UserRequestError: The request does not exist or is no longer pending.
            ValueError: The request is not a plan, or the decision is not valid.
        """
        request = self._store.pending_request(request_id)
        if request.kind != user_request_module.PLAN:
            raise ValueError(
                f'Request {request_id} is a {request.kind}, not a plan'
            )
        response = plan_response_module.PlanResponse(
            request, decision, feedback
        )
        response.check()
        return self._finish(
            request,
            user_request_module.ANSWERED,
            response.stored(),
            response.message(),
            via,
        )

    async def decide_permission(
        self,
        request_id: str,
        decision: str,
        reason: str,
        via: str,
    ) -> user_request_module.UserRequest:
        """Records the decision on a held call, runs the call when it is allowed, and tells the trader.

        Args:
            request_id (str): The request.
            decision (str): "allow_once", "always_allow" or "deny".
            reason (str): Why it was denied, or a note; may be empty.
            via (str): "web", "terminal" or "telegram".

        Returns:
            user_request_module.UserRequest: The decided request.

        Raises:
            user_request_store_module.UserRequestError: The request does not exist, is no longer pending, or has expired.
            ValueError: The request is not a permission request, the decision is not valid, or the trader's tools are not known.
        """
        request = self._store.pending_request(request_id)
        if request.kind != user_request_module.PERMISSION:
            raise ValueError(
                f'Request {request_id} is a {request.kind}, not a permission request'
            )
        response = permission_response_module.PermissionResponse(
            request, decision, reason
        )
        response.check()
        result = None
        if response.allows:
            registry = self._tool_registries.get(request.trader)
            if registry is None:
                raise ValueError(
                    f'The tools of trader {request.trader!r} are not known here'
                )
            if (
                decision == permission_response_module.ALWAYS_ALLOW
                and self._grants is not None
            ):
                self._grants.grant(request.trader, request.content['tool_name'])
            call = messages.ToolCall(
                call_id=str(request.content.get('call_id', request.request_id)),
                name=request.content['tool_name'],
                arguments=dict(request.content.get('arguments') or {}),
            )
            result = await registry.run(call)
        return self._finish(
            request,
            user_request_module.ANSWERED,
            response.stored(result),
            response.message(result),
            via,
        )

    def report_expired(self, request: user_request_module.UserRequest) -> None:
        """Tells the trader that a request lapsed without an answer.

        Args:
            request (user_request_module.UserRequest): The request, already saved as expired.
        """
        if request.kind == user_request_module.PERMISSION:
            message = f'Your request to run {request.title()} (request {request.request_id}) lapsed without an answer, so it was not run. If it still matters, decide again with fresh prices.'
        else:
            message = f'Your {request.kind} "{request.title()}" (request {request.request_id}) lapsed without an answer. Use your own judgment within the rules.'
        self._publish_response(request, user_request_module.EXPIRED, {}, '')
        self._send(request, message)

    def dismiss(
        self, request_id: str, via: str
    ) -> user_request_module.UserRequest:
        """Closes a request without answering it, and tells the trader to use its own judgment.

        Args:
            request_id (str): The request.
            via (str): "web", "terminal" or "telegram".

        Returns:
            user_request_module.UserRequest: The dismissed request.

        Raises:
            user_request_store_module.UserRequestError: The request does not exist or is no longer pending.
        """
        request = self._store.pending_request(request_id)
        message = f'The user closed your {request.kind} "{request.title()}" (request {request.request_id}) without answering. Use your own judgment within the rules, or ask again later if it still matters.'
        return self._finish(
            request,
            user_request_module.DISMISSED,
            {},
            message,
            via,
        )

    def _finish(
        self,
        request: user_request_module.UserRequest,
        status: str,
        response: dict[str, Any],
        message: str,
        via: str,
    ) -> user_request_module.UserRequest:
        """Saves the response, publishes it, and sends the trader its message.

        Args:
            request (user_request_module.UserRequest): The pending request.
            status (str): "answered" or "dismissed".
            response (dict[str, Any]): The response to save.
            message (str): What the trader is told.
            via (str): "web", "terminal" or "telegram".

        Returns:
            user_request_module.UserRequest: The finished request.
        """
        finished = dataclasses.replace(
            request,
            status=status,
            response=response,
            responded_at=datetime.datetime.now(datetime.UTC).isoformat(),
            responded_via=via,
        )
        self._store.save(finished)
        self._publish_response(request, status, response, via)
        self._send(request, message)
        return finished

    def _publish_response(
        self,
        request: user_request_module.UserRequest,
        status: str,
        response: dict[str, Any],
        via: str,
    ) -> None:
        """Publishes how a request was settled, for the web page, Telegram and the journal.

        Args:
            request (user_request_module.UserRequest): The request.
            status (str): "answered", "dismissed" or "expired".
            response (dict[str, Any]): The response saved, or empty.
            via (str): "web", "terminal", "telegram", or empty when it lapsed.
        """
        self._event_bus.publish(
            event_module.Event.now(
                event_module.EventKind.USER_RESPONSE,
                request.trader,
                {
                    'request_id': request.request_id,
                    'kind': request.kind,
                    'status': status,
                    'response': response,
                    'via': via,
                    'title': request.title(),
                },
            )
        )

    def _send(
        self, request: user_request_module.UserRequest, message: str
    ) -> None:
        """Hands the trader a message about its request, as a user message naming the request.

        Args:
            request (user_request_module.UserRequest): The request.
            message (str): What the trader is told.
        """
        trader = self._traders.get(request.trader)
        if trader is None:
            return
        trader.submit(
            trigger_module.Trigger.now(
                trigger_module.TriggerSource.USER_MESSAGE,
                request.trader,
                message,
                request_id=request.request_id,
            )
        )
