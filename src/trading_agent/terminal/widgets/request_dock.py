"""The dock above the message box that holds the desk's pending question, plan or permission request.

It shows one request at a time, permission requests first because they lapse, with "1 of N waiting for you" when more are waiting. The dock never takes the focus by itself: the user presses Tab to answer and Escape to go back, so typing meant for the message box can never answer a request, and Enter can never allow a tool call by accident. A card stays in place while its request is still first, so a half-written answer is not lost when the list is read again.

Typical usage example:

  dock = RequestDock(gateway)
  dock.show(pending_requests)
"""

from typing import Any

from textual import containers
from textual import message
from textual import widgets
from textual.content import Content

from trading_agent.terminal import gateway_client
from trading_agent.terminal.widgets import permission_card
from trading_agent.terminal.widgets import plan_card
from trading_agent.terminal.widgets import question_card


class RequestDock(containers.VerticalScroll):
    """The request dock; hidden while nothing waits."""

    class Answered(message.Message):
        """The shown request was answered, decided or dismissed."""

    class Left(message.Message):
        """The user pressed Escape on a card to go back to the message box."""

    def __init__(self, gateway: gateway_client.GatewayClient):
        """Creates the dock, hidden and empty.

        Args:
            gateway (gateway_client.GatewayClient): The gateway, which the cards send answers to.
        """
        super().__init__(id='request-dock')
        self._gateway = gateway
        self._count = widgets.Static('', classes='request-count')
        self._card: Any = None

    def compose(self):
        """Builds the dock's count line.

        Yields:
            Widget: The count line.
        """
        yield self._count

    def on_mount(self) -> None:
        """Hides the dock until a request waits."""
        self.display = False

    def shown_request_id(self) -> str | None:
        """The request the dock shows.

        Returns:
            str | None: Its id, or None when the dock is empty.
        """
        if self._card is None:
            return None
        return self._card.request_id

    def focus_card(self) -> bool:
        """Puts the focus on the shown card.

        Returns:
            bool: True when there is a card to focus.
        """
        if self._card is None:
            return False
        self._card.focus_card()
        return True

    def show(self, requests: list[dict[str, Any]]) -> bool:
        """Shows the first waiting request, permission requests first.

        Args:
            requests (list[dict[str, Any]]): The desk's pending requests.

        Returns:
            bool: True when a different request is now shown, so the screen can move the focus to it.
        """
        waiting = []
        for request in requests:
            if request.get('kind') == 'permission':
                waiting.append(request)
        for request in requests:
            if request.get('kind') != 'permission':
                waiting.append(request)
        self.display = bool(waiting)
        count = ''
        if len(waiting) > 1:
            count = f'1 of {len(waiting)} waiting for you · '
        self._count.update(
            Content.from_markup(
                '[dim]$count tab to answer · esc to go back to the message box[/dim]',
                count=count,
            )
        )
        if not waiting:
            changed = self._card is not None
            self._remove_card()
            return changed
        first = waiting[0]
        if (
            self._card is not None
            and self._card.request_id == first['request_id']
        ):
            return False
        self._remove_card()
        self._card = self._new_card(first)
        self.mount(self._card)
        return True

    def on_question_card_done(
        self, event: question_card.QuestionCard.Done
    ) -> None:
        """Passes on that the questions were answered.

        Args:
            event (question_card.QuestionCard.Done): The notice.
        """
        event.stop()
        self.post_message(self.Answered())

    def on_plan_card_done(self, event: plan_card.PlanCard.Done) -> None:
        """Passes on that the plan was decided.

        Args:
            event (plan_card.PlanCard.Done): The notice.
        """
        event.stop()
        self.post_message(self.Answered())

    def on_permission_card_done(
        self, event: permission_card.PermissionCard.Done
    ) -> None:
        """Passes on that the permission was decided.

        Args:
            event (permission_card.PermissionCard.Done): The notice.
        """
        event.stop()
        self.post_message(self.Answered())

    def key_escape(self) -> None:
        """Leaves the card for the message box."""
        self.post_message(self.Left())

    def _new_card(self, request: dict[str, Any]) -> Any:
        """Creates the card for a request.

        Args:
            request (dict[str, Any]): The request.

        Returns:
            Any: A question, plan or permission card.
        """
        kind = request.get('kind')
        if kind == 'permission':
            return permission_card.PermissionCard(request, self._gateway)
        if kind == 'plan':
            return plan_card.PlanCard(request, self._gateway)
        return question_card.QuestionCard(request, self._gateway)

    def _remove_card(self) -> None:
        """Removes the shown card, if any."""
        if self._card is not None:
            self._card.remove()
            self._card = None
