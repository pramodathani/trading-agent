"""The side panel's Desk card: the desk's name, state, waiting triggers, exchanges and session.

Typical usage example:

  card = DeskCard()
  card.show(desk_summary)
"""

from typing import Any

from textual.content import Content

from trading_agent.terminal.widgets import side_card


class DeskCard(side_card.SideCard):
    """The Desk card."""

    def __init__(self, collapsed: bool = False):
        """Creates the card.

        Args:
            collapsed (bool): Whether it starts folded.
        """
        super().__init__('desk', 'Desk', collapsed=collapsed)

    def show(self, desk: dict[str, Any] | None, mode: str) -> None:
        """Shows the desk's state.

        Args:
            desk (dict[str, Any] | None): The desk summary, or None while loading.
            mode (str): "dry_run" or "live".
        """
        if desk is None:
            self.show_body(self.note('Loading…'))
            return
        self.show_aside('LIVE' if mode == 'live' else 'DRY RUN')
        state = str(desk.get('state', ''))
        if desk.get('paused'):
            state += ', paused'
        state_value = Content(state)
        if desk.get('state') != 'idle':
            state_value = Content.from_markup(
                '[$warning]$state[/]', state=state
            )
        self.show_body(
            self.rows(
                [
                    (
                        'Name',
                        desk.get('name', ''),
                    ),
                    (
                        'State',
                        state_value,
                    ),
                    (
                        'Waiting triggers',
                        str(desk.get('queued', 0)),
                    ),
                    (
                        'Exchanges',
                        str(desk.get('exchanges', 0)),
                    ),
                    (
                        'Session',
                        str(desk.get('session_id') or '—'),
                    ),
                ]
            )
        )
