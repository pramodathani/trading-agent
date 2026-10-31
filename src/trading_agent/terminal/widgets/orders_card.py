"""The side panel's Orders and trades card: today's orders placed and cancelled, trades, open orders and stocks held.

The counts of orders and trades come from today's events of the trader, as on the web page; open orders and stocks held come from the gateway.

Typical usage example:

  card = OrdersCard()
  card.show('general', events, open_orders, account)
"""

from collections.abc import Sequence
from typing import Any

from trading_agent.terminal.widgets import side_card


class OrdersCard(side_card.SideCard):
    """The Orders and trades card."""

    def __init__(self, collapsed: bool = False):
        """Creates the card.

        Args:
            collapsed (bool): Whether it starts folded.
        """
        super().__init__('orders', 'Orders and trades', collapsed=collapsed)
        self.show_aside('today')

    def show(
        self,
        trader_name: str,
        events: Sequence[dict[str, Any]],
        open_orders: list[dict[str, Any]] | None,
        account: dict[str, Any] | None,
    ) -> None:
        """Shows the counts.

        Args:
            trader_name (str): The trader the chat shows.
            events (Sequence[dict[str, Any]]): The trader's events of today.
            open_orders (list[dict[str, Any]] | None): The trader's open orders, or None when not known.
            account (dict[str, Any] | None): The account, or None when not known.
        """
        placed = 0
        cancelled = 0
        trades = 0
        for event in events:
            payload = event.get('payload') or {}
            if (
                event.get('kind') == 'order'
                and payload.get('action') == 'placed'
            ):
                placed += 1
            if (
                event.get('kind') == 'order'
                and payload.get('action') == 'cancelled'
            ):
                cancelled += 1
            if event.get('kind') == 'fill':
                try:
                    filled = float(payload.get('filled_quantity') or 0)
                except TypeError, ValueError:
                    filled = 0
                if filled > 0:
                    trades += 1
        open_count = '—'
        if open_orders is not None:
            open_count = str(len(open_orders))
        held = '—'
        if account is not None:
            count = 0
            for owner in account.get('owners') or []:
                if owner.get('trader') == trader_name:
                    count += 1
            held = str(count)
        self.show_body(
            self.rows(
                [
                    (
                        'Orders placed',
                        str(placed),
                    ),
                    (
                        'Orders cancelled',
                        str(cancelled),
                    ),
                    (
                        'Trades (fills)',
                        str(trades),
                    ),
                    (
                        'Open orders',
                        open_count,
                    ),
                    (
                        'Stocks held',
                        held,
                    ),
                ]
            )
        )
