"""The user's decision on a trader's plan: approve it, or ask for changes with feedback.

Typical usage example:

  response = PlanResponse(request, 'revise', 'Smaller size on the first trade')
  response.check()
  text = response.message()
"""

from typing import Any

from trading_agent.requests import user_request as user_request_module

APPROVE = 'approve'
REVISE = 'revise'


class PlanResponse:
    """Approve, or keep planning with the user's feedback."""

    def __init__(
        self,
        request: user_request_module.UserRequest,
        decision: str,
        feedback: str,
    ):
        """Creates the response.

        Args:
            request (user_request_module.UserRequest): The plan request.
            decision (str): "approve" or "revise".
            feedback (str): What the user wants changed, or a note with an approval.
        """
        self._request = request
        self._decision = decision
        self._feedback = feedback.strip()

    def check(self) -> None:
        """Checks the decision.

        Raises:
            ValueError: The decision is neither "approve" nor "revise", or a revision has no feedback.
        """
        if self._decision not in (APPROVE, REVISE):
            raise ValueError(
                f'A plan is approved or revised, not {self._decision!r}'
            )
        if self._decision == REVISE and not self._feedback:
            raise ValueError('Say what should change in the plan')

    def stored(self) -> dict[str, Any]:
        """The response as saved with the request.

        Returns:
            dict[str, Any]: The decision and the feedback.
        """
        return {
            'decision': self._decision,
            'feedback': self._feedback,
        }

    def message(self) -> str:
        """The message the trader receives.

        Returns:
            str: The decision, with the feedback.
        """
        title = self._request.title()
        if self._decision == APPROVE:
            text = f'The user approved your plan "{title}" (request {self._request.request_id}). Carry it out within the rules.'
            if self._feedback:
                text = f'{text}\nThey added: {self._feedback}'
            return text
        return f'The user wants changes to your plan "{title}" (request {self._request.request_id}) before you act on it:\n{self._feedback}\nRevise the plan and present it again with present_plan.'
