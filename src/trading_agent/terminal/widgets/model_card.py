"""The side panel's Model card: which backend answered last, the actual model, the preference and the model order.

Typical usage example:

  card = ModelCard()
  card.show(trader_summary, context_usage)
"""

import re
from typing import Any

from textual.content import Content

from trading_agent.terminal.widgets import side_card

_ORDER_NUMBER = re.compile(r'^\d+\.\s*')


class ModelCard(side_card.SideCard):
    """The Model card."""

    def __init__(self, collapsed: bool = False):
        """Creates the card.

        Args:
            collapsed (bool): Whether it starts folded.
        """
        super().__init__('model', 'Model', collapsed=collapsed)

    def show(
        self,
        trader: dict[str, Any] | None,
        usage: dict[str, Any] | None,
    ) -> None:
        """Shows the trader's models.

        Args:
            trader (dict[str, Any] | None): The trader summary, or None while loading.
            usage (dict[str, Any] | None): The context usage snapshot, which names the actual model, or None.
        """
        if trader is None:
            self.show_body(self.note('Loading…'))
            return
        rows = [
            (
                'Answered last',
                str(
                    trader.get('last_model')
                    or trader.get('preferred_model')
                    or '—'
                ),
            ),
        ]
        if usage is not None and usage.get('model'):
            rows.append(
                (
                    'Model',
                    str(usage['model']),
                )
            )
        rows.append(
            (
                'Preferred',
                str(trader.get('preferred_model') or 'configured order'),
            )
        )
        parts = [
            self.rows(rows),
        ]
        for number, line in enumerate(trader.get('models') or [], start=1):
            parts.append(
                Content.from_markup(
                    '[dim]$number.[/dim] $line',
                    number=str(number),
                    line=_ORDER_NUMBER.sub('', str(line)),
                )
            )
        self.show_body(Content('\n').join(parts))
