"""The side panel's Trader card: the trader's name, state, waiting triggers, exchanges and session.

Typical usage example:

  card = TraderCard()
  card.show(trader_summary)
"""

from typing import Any

from textual.content import Content

from trading_agent.terminal.widgets import side_card


class TraderCard(side_card.SideCard):
    """The Trader card."""

    def __init__(self, collapsed: bool = False):
        """Creates the card.

        Args:
            collapsed (bool): Whether it starts folded.
        """
        super().__init__('trader', 'Trader', collapsed=collapsed)

    def show(self, trader: dict[str, Any] | None, mode: str) -> None:
        """Shows the trader's state.

        Args:
            trader (dict[str, Any] | None): The trader summary, or None while loading.
            mode (str): "dry_run" or "live".
        """
        if trader is None:
            self.show_body(self.note('Loading…'))
            return
        self.show_aside('LIVE' if mode == 'live' else 'DRY RUN')
        state = str(trader.get('state', ''))
        if trader.get('paused'):
            state += ', paused'
        state_value = Content(state)
        if trader.get('state') != 'idle':
            state_value = Content.from_markup(
                '[$warning]$state[/]', state=state
            )
        self.show_body(
            self.rows(
                [
                    (
                        'Name',
                        trader.get('name', ''),
                    ),
                    (
                        'State',
                        state_value,
                    ),
                    (
                        'Waiting triggers',
                        str(trader.get('queued', 0)),
                    ),
                    (
                        'Exchanges',
                        str(trader.get('exchanges', 0)),
                    ),
                    (
                        'Session',
                        str(trader.get('session_id') or '—'),
                    ),
                ]
            )
        )
