"""The card for a plan a trader presents for approval (present_plan), as the web page's PlanCard.tsx shows it.

The plan is drawn as Markdown. The user approves it, optionally with notes, or sends it back with feedback, which "Keep planning" requires. The trader does not act on the plan until it is approved.

Keys: 1 or Enter on "Approve" approves, 2 keeps planning, Tab moves to the feedback box and back, Ctrl+X dismisses without deciding. Typing a letter while the choices have the focus goes into the feedback box.

Typical usage example:

  card = PlanCard(request, gateway)
"""

from typing import Any, ClassVar

from textual import binding
from textual import containers
from textual import events
from textual import message
from textual import widgets
from textual import work
from textual.content import Content
from textual.widgets import option_list

from trading_agent.terminal import gateway_client

_DECISIONS = (
    'approve',
    'revise',
)


class PlanCard(containers.Vertical):
    """A card for approving or revising the trader's plan."""

    can_focus = True

    BINDINGS: ClassVar[list[binding.BindingType]] = [
        binding.Binding('tab', 'focus_box', 'To the feedback box', show=False),
        binding.Binding('ctrl+x', 'dismiss_request', 'Dismiss', show=False),
    ]

    class Done(message.Message):
        """The request was decided or dismissed."""

    def __init__(
        self,
        request: dict[str, Any],
        gateway: gateway_client.GatewayClient,
    ):
        """Creates the card.

        Args:
            request (dict[str, Any]): The pending plan request.
            gateway (gateway_client.GatewayClient): The gateway, to send the decision.
        """
        super().__init__(classes='request-card plan-card')
        self.request_id = request['request_id']
        self._request = request
        self._gateway = gateway
        self._sending = False

    def compose(self):
        """Builds the card.

        Yields:
            Widget: The heading, title, plan, choices, feedback box, error and hint.
        """
        content = self._request.get('content') or {}
        yield widgets.Static(
            Content.from_markup(
                '[b]$trader[/b] presents a plan for your approval',
                trader=self._request.get('trader', ''),
            ),
            classes='request-heading',
        )
        yield widgets.Static(
            Content.from_markup(
                '[b]$title[/b]', title=content.get('title', '')
            ),
            classes='question-text',
        )
        with containers.VerticalScroll(classes='plan-body'):
            yield widgets.Markdown(content.get('plan', ''))
        yield widgets.OptionList(
            option_list.Option(
                Content.from_markup(
                    '1  [b]Approve[/b]  [dim]the trader may act on the plan; feedback is optional[/dim]'
                )
            ),
            option_list.Option(
                Content.from_markup(
                    '2  [b]Keep planning[/b]  [dim]send it back with the feedback below[/dim]'
                )
            ),
            classes='question-options',
        )
        yield widgets.Input(
            placeholder='Feedback for the trader: needed for Keep planning, optional with Approve',
            classes='plan-feedback',
            select_on_focus=False,
        )
        yield widgets.Static('', classes='request-error')
        yield widgets.Static(
            '[dim]↑↓ to move · enter or 1-2 to choose · tab to the feedback box · ctrl+x to dismiss[/dim]',
            classes='request-hint',
        )

    def focus_card(self) -> None:
        """Puts the focus on the choices, so the card's keys work."""
        self.query_one('.question-options', widgets.OptionList).focus()

    def on_key(self, event: events.Key) -> None:
        """Decides with a number key.

        Args:
            event (events.Key): The key press.
        """
        if isinstance(self.screen.focused, widgets.Input):
            return
        if (
            event.is_printable
            and event.character
            and not event.character.isdigit()
        ):
            event.stop()
            box = self.query_one('.plan-feedback', widgets.Input)
            box.focus()
            box.insert_text_at_cursor(event.character)
            return
        if event.character in ('1', '2'):
            event.stop()
            self._decide(_DECISIONS[int(event.character) - 1])

    def action_focus_box(self) -> None:
        """Moves to the feedback box, or back to the choices from it."""
        box = self.query_one('.plan-feedback', widgets.Input)
        if self.screen.focused is box:
            self.focus_card()
            return
        box.focus()

    def on_option_list_option_selected(
        self, event: widgets.OptionList.OptionSelected
    ) -> None:
        """Decides with the selected choice.

        Args:
            event (widgets.OptionList.OptionSelected): The selection.
        """
        event.stop()
        self._decide(_DECISIONS[event.option_index])

    def on_input_submitted(self, event: widgets.Input.Submitted) -> None:
        """Sends the plan back with the feedback when Enter is pressed in the box.

        Args:
            event (widgets.Input.Submitted): The submission.
        """
        event.stop()
        if event.value.strip():
            self._decide('revise')

    def action_dismiss_request(self) -> None:
        """Dismisses the plan without deciding; the trader uses its own judgment."""
        self._dismiss()

    def _decide(self, decision: str) -> None:
        """Checks the decision and sends it.

        Args:
            decision (str): "approve" or "revise".
        """
        feedback = self.query_one('.plan-feedback', widgets.Input).value.strip()
        if decision == 'revise' and not feedback:
            self._error(
                'Say what should change in the feedback box, then choose Keep planning.'
            )
            self.query_one('.plan-feedback', widgets.Input).focus()
            return
        self._send(decision, feedback)

    @work(exclusive=True, group='answer')
    async def _send(self, decision: str, feedback: str) -> None:
        """Sends the decision to the gateway.

        Args:
            decision (str): "approve" or "revise".
            feedback (str): The feedback.
        """
        if self._sending:
            return
        self._sending = True
        try:
            await self._gateway.decide_plan(self.request_id, decision, feedback)
        except gateway_client.GatewayError as error:
            self._sending = False
            self._error(error.message)
            return
        self.post_message(self.Done())

    @work(exclusive=True, group='answer')
    async def _dismiss(self) -> None:
        """Dismisses the request at the gateway."""
        try:
            await self._gateway.dismiss_request(self.request_id)
        except gateway_client.GatewayError as error:
            self._error(error.message)
            return
        self.post_message(self.Done())

    def _error(self, text: str) -> None:
        """Shows a problem on the card.

        Args:
            text (str): The problem.
        """
        self.query_one('.request-error', widgets.Static).update(
            Content.from_markup('[$error]$text[/]', text=text)
        )
