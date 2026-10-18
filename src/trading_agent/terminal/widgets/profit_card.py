"""The side panel's Profit and loss card: the desk's and the account's profit, and any halts in force.

Typical usage example:

  card = ProfitCard()
  card.show('general', account)
"""

from typing import Any

from textual.content import Content

from trading_agent.terminal import formatter
from trading_agent.terminal.widgets import side_card


class ProfitCard(side_card.SideCard):
    """The Profit and loss card."""

    def __init__(self, collapsed: bool = False):
        """Creates the card.

        Args:
            collapsed (bool): Whether it starts folded.
        """
        super().__init__('pnl', 'Profit and loss', collapsed=collapsed)
        self._formatter = formatter.Formatter()

    def show(self, desk_name: str, account: dict[str, Any] | None) -> None:
        """Shows the profit and loss.

        Args:
            desk_name (str): The desk the chat shows.
            account (dict[str, Any] | None): The account, or None when it could not be read.
        """
        if account is None:
            self.show_body(self.note('Loading…'))
            return
        desk_pnl = float((account.get('desk_pnl') or {}).get(desk_name) or 0)
        lines = [
            self.rows(
                [
                    (
                        'This desk today',
                        self._signed(desk_pnl),
                    ),
                    (
                        'Account today',
                        self._signed(float(account.get('day_pnl') or 0)),
                    ),
                    (
                        'Account this week',
                        self._signed(float(account.get('week_pnl') or 0)),
                    ),
                ]
            ),
        ]
        for halt in account.get('halts') or []:
            scope = halt.get('scope')
            if scope not in (desk_name, 'account'):
                continue
            who = 'Desk'
            if scope == 'account':
                who = 'Account'
            lines.append(
                Content.from_markup(
                    '[$error]$who halted until $until: $reason[/]',
                    who=who,
                    until=str(halt.get('until_date', '')),
                    reason=str(halt.get('reason', '')),
                )
            )
        self.show_body(Content('\n').join(lines))

    def _signed(self, amount: float) -> Content:
        """An amount with its sign, green for a profit and red for a loss.

        Args:
            amount (float): The amount in rupees.

        Returns:
            Content: The coloured amount.
        """
        text = self._formatter.signed_money(amount)
        if amount > 0:
            return Content.from_markup('[$success]$text[/]', text=text)
        if amount < 0:
            return Content.from_markup('[$error]$text[/]', text=text)
        return Content(text)
