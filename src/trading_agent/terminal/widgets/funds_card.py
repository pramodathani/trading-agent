"""The side panel's Funds card: the balance and the margin in use, with a meter.

Typical usage example:

  card = FundsCard()
  card.show(account, None)
"""

from typing import Any

from textual.content import Content

from trading_agent.terminal import formatter
from trading_agent.terminal.widgets import side_card

_METER_WIDTH = 36


class FundsCard(side_card.SideCard):
    """The Funds card."""

    def __init__(self, collapsed: bool = False):
        """Creates the card.

        Args:
            collapsed (bool): Whether it starts folded.
        """
        super().__init__('funds', 'Funds', collapsed=collapsed)
        self._formatter = formatter.Formatter()

    def show(self, account: dict[str, Any] | None, error: str | None) -> None:
        """Shows the account's funds.

        Args:
            account (dict[str, Any] | None): The account, or None when it could not be read.
            error (str | None): Why it could not be read, or None while loading.
        """
        if account is None:
            self.show_body(self.note(error or 'Loading…'))
            return
        balance = float(account.get('total_balance') or 0)
        margin = float(account.get('margin_utilized') or 0)
        share = 0.0
        if balance > 0:
            share = min(1.0, margin / balance)
        cells = round(_METER_WIDTH * share)
        meter = Content.assemble(
            ('█' * cells, '$accent'),
            ('░' * (_METER_WIDTH - cells), 'dim'),
        )
        self.show_body(
            Content('\n').join(
                [
                    self.rows(
                        [
                            (
                                'Balance',
                                self._formatter.money(balance),
                            ),
                            (
                                'Margin in use',
                                self._formatter.money(margin),
                            ),
                        ]
                    ),
                    meter,
                    self.note(
                        f'{self._formatter.share(margin, balance)} of the balance is in use as margin.'
                    ),
                ]
            )
        )
