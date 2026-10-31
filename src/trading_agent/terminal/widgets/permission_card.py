"""The card for a tool call that needs the user's permission, as the web page's PermissionCard.tsx and Claude Code show it.

The card names the tool and its arguments and counts down to the moment the request lapses. The choices are Yes (once), Yes and don't ask again for this tool on this trader (until revoked on the Settings screen), and No with an optional reason that goes to the trader.

Keys: Up and Down move, Enter or 1 to 3 decides, Tab moves to the reason box and back. Typing a letter while the choices have the focus goes into the reason box, so a reason being typed can never be lost and Enter can never pick Yes in its place.

Typical usage example:

  card = PermissionCard(request, gateway)
"""

import datetime
import json
from typing import Any, ClassVar

from textual import binding
from textual import containers
from textual import events
from textual import message
from textual import widgets
from textual import work
from textual.content import Content
from textual.widgets import option_list

from trading_agent.terminal import formatter
from trading_agent.terminal import gateway_client

_DECISIONS = (
    'allow_once',
    'always_allow',
    'deny',
)
_URGENT_SECONDS = 60


class PermissionCard(containers.Vertical):
    """A card for allowing or denying one tool call."""

    can_focus = True

    BINDINGS: ClassVar[list[binding.BindingType]] = [
        binding.Binding('tab', 'focus_box', 'To the reason box', show=False),
    ]

    class Done(message.Message):
        """The request was decided."""

    def __init__(
        self,
        request: dict[str, Any],
        gateway: gateway_client.GatewayClient,
    ):
        """Creates the card.

        Args:
            request (dict[str, Any]): The pending permission request.
            gateway (gateway_client.GatewayClient): The gateway, to send the decision.
        """
        super().__init__(classes='request-card permission-card')
        self.request_id = request['request_id']
        self._request = request
        self._gateway = gateway
        self._sending = False
        self._formatter = formatter.Formatter()

    def compose(self):
        """Builds the card.

        Yields:
            Widget: The heading with the countdown, the tool and its arguments, the choices, the reason box, the error and the hint.
        """
        content = self._request.get('content') or {}
        tool_name = content.get('tool_name', 'a tool')
        trader = self._request.get('trader', '')
        yield widgets.Static('', classes='request-heading')
        yield widgets.Static(
            Content.from_markup('Run [b $accent]$tool[/]?', tool=tool_name),
            classes='question-text',
        )
        yield widgets.Static(
            json.dumps(
                content.get('arguments') or {}, indent=2, ensure_ascii=False
            ),
            markup=False,
            classes='permission-arguments',
        )
        yield widgets.OptionList(
            option_list.Option(
                Content.from_markup(
                    '1  [b]Yes[/b]  [dim]run this call once, through the risk engine as usual[/dim]'
                )
            ),
            option_list.Option(
                Content.from_markup(
                    "2  [b]Yes, and don't ask again for $tool on $trader[/b]  [dim]until you revoke it on Settings[/dim]",
                    tool=tool_name,
                    trader=trader,
                )
            ),
            option_list.Option(
                Content.from_markup(
                    '3  [b]No[/b]  [dim]tell the trader why in the box below (optional)[/dim]'
                )
            ),
            classes='question-options',
        )
        yield widgets.Input(
            placeholder='Reason for No, sent to the trader (optional)',
            classes='permission-reason',
            select_on_focus=False,
        )
        yield widgets.Static('', classes='request-error')
        yield widgets.Static(
            '[dim]↑↓ to move · enter or 1-3 to decide · tab to the reason box[/dim]',
            classes='request-hint',
        )

    def on_mount(self) -> None:
        """Starts the countdown."""
        self._show_countdown()
        self.set_interval(1.0, self._show_countdown)

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
            box = self.query_one('.permission-reason', widgets.Input)
            box.focus()
            box.insert_text_at_cursor(event.character)
            return
        if event.character in ('1', '2', '3'):
            event.stop()
            self._decide(_DECISIONS[int(event.character) - 1])

    def action_focus_box(self) -> None:
        """Moves to the reason box, or back to the choices from it."""
        box = self.query_one('.permission-reason', widgets.Input)
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
        """Denies with the typed reason when Enter is pressed in the box.

        Args:
            event (widgets.Input.Submitted): The submission.
        """
        event.stop()
        self._decide('deny')

    def _decide(self, decision: str) -> None:
        """Sends the decision unless the request has lapsed.

        Args:
            decision (str): "allow_once", "always_allow" or "deny".
        """
        if self._seconds_left() == 0:
            self._error('This request has lapsed; the trader was told no.')
            return
        reason = self.query_one('.permission-reason', widgets.Input).value
        self._send(decision, reason.strip())

    @work(exclusive=True, group='answer')
    async def _send(self, decision: str, reason: str) -> None:
        """Sends the decision to the gateway.

        Args:
            decision (str): "allow_once", "always_allow" or "deny".
            reason (str): The reason, for a denial.
        """
        if self._sending:
            return
        self._sending = True
        try:
            await self._gateway.decide_permission(
                self.request_id, decision, reason
            )
        except gateway_client.GatewayError as error:
            self._sending = False
            self._error(error.message)
            return
        self.post_message(self.Done())

    def _show_countdown(self) -> None:
        """Redraws the heading with the time left."""
        seconds = self._seconds_left()
        countdown = ''
        if seconds is not None and seconds == 0:
            countdown = '[$error]lapsed[/]'
        elif seconds is not None:
            colour = '$text-muted'
            if seconds < _URGENT_SECONDS:
                colour = '$warning'
            countdown = (
                f'[{colour}]lapses in {seconds // 60}:{seconds % 60:02d}[/]'
            )
        self.query_one('.request-heading', widgets.Static).update(
            Content.from_markup(
                f'[b]$trader[/b] needs your permission   {countdown}',
                trader=self._request.get('trader', ''),
            )
        )

    def _seconds_left(self) -> int | None:
        """The seconds until the request lapses.

        Returns:
            int | None: The seconds, 0 once lapsed, or None when it never lapses.
        """
        expires_at = self._request.get('expires_at')
        if not expires_at:
            return None
        moment = self._formatter.moment(expires_at)
        if moment is None:
            return None
        now = datetime.datetime.now(datetime.UTC)
        return max(0, int((moment - now).total_seconds()))

    def _error(self, text: str) -> None:
        """Shows a problem on the card.

        Args:
            text (str): The problem.
        """
        self.query_one('.request-error', widgets.Static).update(
            Content.from_markup('[$error]$text[/]', text=text)
        )
