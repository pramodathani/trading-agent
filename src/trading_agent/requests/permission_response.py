"""The user's decision on a held tool call: allow it once, always allow it, or deny it.

Typical usage example:

  response = PermissionResponse(request, 'deny', 'Not today')
  response.check()
  text = response.message(None)
"""

from typing import Any

from trading_agent.requests import user_request as user_request_module
from trading_agent.tools import tool as tool_module

ALLOW_ONCE = 'allow_once'
ALWAYS_ALLOW = 'always_allow'
DENY = 'deny'
DECISIONS = (
    ALLOW_ONCE,
    ALWAYS_ALLOW,
    DENY,
)


class PermissionResponse:
    """Allow once, always allow, or deny, with the user's reason for a denial."""

    def __init__(
        self,
        request: user_request_module.UserRequest,
        decision: str,
        reason: str,
    ):
        """Creates the response.

        Args:
            request (user_request_module.UserRequest): The permission request.
            decision (str): "allow_once", "always_allow" or "deny".
            reason (str): Why it was denied, or what the desk should do instead; may be empty.
        """
        self._request = request
        self.decision = decision
        self._reason = reason.strip()

    @property
    def allows(self) -> bool:
        """Whether the held call is to be run."""
        return self.decision in (ALLOW_ONCE, ALWAYS_ALLOW)

    def check(self) -> None:
        """Checks the decision.

        Raises:
            ValueError: The decision is not one of DECISIONS.
        """
        if self.decision not in DECISIONS:
            raise ValueError(f'Permission is allow_once, always_allow or deny, not {self.decision!r}')

    def stored(self, result: tool_module.ToolResult | None) -> dict[str, Any]:
        """The response as saved with the request.

        Args:
            result (tool_module.ToolResult | None): What the call returned when it was run, or None.

        Returns:
            dict[str, Any]: The decision, the reason and the call's result.
        """
        stored = {
            'decision': self.decision,
            'reason': self._reason,
        }
        if result is not None:
            stored['result'] = result.text
            stored['result_is_error'] = result.is_error
        return stored

    def message(self, result: tool_module.ToolResult | None) -> str:
        """The message the desk receives.

        Args:
            result (tool_module.ToolResult | None): What the call returned when it was run, or None when it was denied.

        Returns:
            str: The decision and, when the call was run, its result.
        """
        tool_name = self._request.content['tool_name']
        request_id = self._request.request_id
        if not self.allows or result is None:
            text = f'The user denied {tool_name} (request {request_id}), so it was not run.'
            if self._reason:
                text = f'{text} Their reason: {self._reason}'
            return f'{text} Do not try to reach the same result another way; ask them if it still matters.'
        outcome = 'failed' if result.is_error else 'was run'
        text = f'The user allowed {tool_name} (request {request_id}), and the harness ran it with the arguments you gave. It {outcome}:\n{result.text}'
        if self.decision == ALWAYS_ALLOW:
            text = f'{text}\nThey also allowed you to use {tool_name} without asking from now on.'
        if self._reason:
            text = f'{text}\nThey added: {self._reason}'
        return text
