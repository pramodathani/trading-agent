"""The Trading page: each trader's profit and stocks, halts, positions, the traders' open orders, UBI's order book, and the kill switch.

It copies the web page's TradingPage.tsx. The kill switch halts every trader and flattens the account; like the web page, it asks for a reason and the typed word FLATTEN.

Typical usage example:

  app.push_screen(TradingScreen('general'))
"""

from typing import Any, ClassVar

from textual import binding
from textual import containers
from textual import widgets
from textual import work
from textual.content import Content

from trading_agent.terminal import formatter
from trading_agent.terminal import gateway_client
from trading_agent.terminal.screens import page_screen
from trading_agent.terminal.widgets import confirm_dialog

_ORDER_BOOK_KINDS = (
    'orders',
    'trades',
    'open_parents',
)


class TradingScreen(page_screen.PageScreen):
    """The Trading page."""

    TITLE_TEXT = 'Trading'
    REFRESH_SECONDS = 15.0

    BINDINGS: ClassVar[list[binding.BindingType]] = [
        binding.Binding('l', 'load_order_book', "Load UBI's order book"),
        binding.Binding('k', 'next_book_kind', 'Orders, trades or parents'),
        binding.Binding('K', 'kill_switch', 'Fire the kill switch'),
    ]

    def __init__(self, trader_name: str):
        """Creates the page.

        Args:
            trader_name (str): The trader the chat shows.
        """
        super().__init__(trader_name)
        self._formatter = formatter.Formatter()
        self._book_kind = _ORDER_BOOK_KINDS[0]

    def compose_page(self):
        """Builds the page's sections.

        Yields:
            Widget: The sections, in a scroll area.
        """
        with containers.VerticalScroll(classes='page-body'):
            yield widgets.Static('[b]Traders[/b]', classes='page-heading')
            yield widgets.DataTable(id='trading-traders', cursor_type='row')
            yield widgets.Static('', id='trading-halts')
            yield widgets.Static('[b]Positions[/b]', classes='page-heading')
            yield widgets.DataTable(id='trading-positions', cursor_type='row')
            yield widgets.Static(
                "[b]Traders' open orders[/b]", classes='page-heading'
            )
            yield widgets.DataTable(id='trading-orders', cursor_type='row')
            yield widgets.Static(
                '', id='trading-book-title', classes='page-heading'
            )
            yield widgets.DataTable(id='trading-book', cursor_type='row')
            yield widgets.Static(
                '[b $error]Kill switch[/]  [dim]K halts every trader and flattens the account; it asks for a reason and the word FLATTEN.[/dim]',
                classes='page-heading',
            )

    def on_mount(self) -> None:
        """Sets up the tables' columns, then reads the data."""
        self.table('trading-traders').add_columns(
            'Trader',
            'Today',
            'Stocks owned',
        )
        self.table('trading-positions').add_columns(
            'Symbol',
            'Product',
            'Trader',
            'Quantity',
            'Last price',
            'Today',
        )
        self.table('trading-orders').add_columns(
            'Trader',
            'Symbol',
            'Side',
            'Quantity',
            'Price',
            'Kind',
            'State',
            'Placed',
        )
        self.table('trading-book').add_columns(
            'Order',
            'Symbol',
            'Side',
            'Status',
            'Filled',
            'Average price',
            'Message',
        )
        self._show_book_title('press l to load it')
        super().on_mount()

    @work(exclusive=True, group='page')
    async def refresh_page(self) -> None:
        """Reads the account and the traders' open orders."""
        gateway = self.app.gateway
        try:
            account = await gateway.account()
            trader_orders = await gateway.trader_orders()
        except gateway_client.GatewayError as error:
            self.problem(error.message)
            return
        self._show_traders(account)
        self._show_positions(account)
        self._show_orders(trader_orders)

    def action_load_order_book(self) -> None:
        """Loads UBI's own order book of the chosen kind."""
        self._load_book()

    def action_next_book_kind(self) -> None:
        """Switches between orders, trades and open parent orders, and loads them."""
        index = _ORDER_BOOK_KINDS.index(self._book_kind)
        self._book_kind = _ORDER_BOOK_KINDS[
            (index + 1) % len(_ORDER_BOOK_KINDS)
        ]
        self._load_book()

    def action_kill_switch(self) -> None:
        """Asks for a reason and FLATTEN, then fires the kill switch."""

        def fire(reason: str | None) -> None:
            """Fires once confirmed.

            Args:
                reason (str | None): The reason, or None when cancelled.
            """
            if reason is not None:
                self._fire(reason)

        self.app.push_screen(
            confirm_dialog.ConfirmDialog(
                'Fire the kill switch',
                'Every trader is halted and the whole account is flattened: open orders are cancelled and positions closed. This cannot be undone from here.',
                'Fire',
                word='FLATTEN',
            ),
            fire,
        )

    @work(group='action')
    async def _fire(self, reason: str) -> None:
        """Fires the kill switch and shows its report.

        Args:
            reason (str): Why, for the journal.
        """
        try:
            report = await self.app.gateway.kill(reason)
        except gateway_client.GatewayError as error:
            self.problem(error.message)
            return
        self.notify(
            str(report.get('text') or report),
            title='Kill switch fired',
            severity='warning',
            timeout=15,
        )
        self.refresh_page()

    @work(exclusive=True, group='book')
    async def _load_book(self) -> None:
        """Reads UBI's order book."""
        self._show_book_title('loading…')
        try:
            answer = await self.app.gateway.broker_orders(self._book_kind)
        except gateway_client.GatewayError as error:
            self._show_book_title(f'could not load: {error.message}')
            return
        rows = answer.get(self._book_kind) or []
        table = self.table('trading-book')
        table.clear()
        for row in rows:
            table.add_row(
                str(row.get('order_id') or row.get('id') or ''),
                str(row.get('symbol') or row.get('trading_symbol') or ''),
                str(row.get('transaction_type') or row.get('side') or ''),
                str(row.get('status') or ''),
                str(row.get('filled_quantity') or ''),
                self._formatter.price_text(row.get('average_price')),
                str(row.get('status_message') or row.get('message') or '')[:60],
            )
        self._show_book_title(
            f'{len(rows)} rows as of {answer.get("as_of", "")}'
        )

    def _show_book_title(self, state: str) -> None:
        """Redraws the order book's heading.

        Args:
            state (str): What the table holds now.
        """
        self.query_one('#trading-book-title', widgets.Static).update(
            Content.from_markup(
                "[b]UBI's order book: $kind[/b]  [dim]$state · l load · k orders, trades or parents[/dim]",
                kind=self._book_kind.replace('_', ' '),
                state=state,
            )
        )

    def _show_traders(self, account: dict[str, Any]) -> None:
        """Fills the traders table and the halts line.

        Args:
            account (dict[str, Any]): The account.
        """
        owned: dict[str, list[str]] = {}
        for owner in account.get('owners') or []:
            owned.setdefault(owner.get('trader', ''), []).append(
                owner.get('symbol', '')
            )
        table = self.table('trading-traders')
        table.clear()
        names = []
        for trader in self.app.traders_document.get('traders', []):
            names.append(trader.get('name', ''))
        for name in names:
            table.add_row(
                name,
                self._formatter.signed_money(
                    (account.get('trader_pnl') or {}).get(name, 0.0)
                ),
                ', '.join(owned.get(name, [])) or '—',
            )
        lines = []
        for halt in account.get('halts') or []:
            lines.append(
                Content.from_markup(
                    '[$error]$scope halted until $until: $reason[/]',
                    scope=str(halt.get('scope', '')),
                    until=str(halt.get('until_date', '')),
                    reason=str(halt.get('reason', '')),
                )
            )
        if not lines:
            lines.append(Content.from_markup('[dim]No halts in force.[/dim]'))
        self.query_one('#trading-halts', widgets.Static).update(
            Content('\n').join(lines)
        )

    def _show_positions(self, account: dict[str, Any]) -> None:
        """Fills the positions table.

        Args:
            account (dict[str, Any]): The account.
        """
        owners = {}
        for owner in account.get('owners') or []:
            owners[owner.get('instrument_id')] = owner.get('trader', '')
        table = self.table('trading-positions')
        table.clear()
        for position in account.get('positions') or []:
            table.add_row(
                str(position.get('symbol', '')),
                str(position.get('product', '')),
                owners.get(position.get('instrument_id'), 'yours'),
                str(position.get('quantity', '')),
                self._formatter.price_text(position.get('last_price')),
                self._formatter.signed_money(position.get('day_pnl')),
            )

    def _show_orders(self, trader_orders: dict[str, Any]) -> None:
        """Fills the traders' open orders table.

        Args:
            trader_orders (dict[str, Any]): The open orders, keyed by trader.
        """
        table = self.table('trading-orders')
        table.clear()
        for trader_name, orders in trader_orders.items():
            for order in orders or []:
                kind = str(order.get('kind', ''))
                if order.get('dry_run'):
                    kind += ' (dry run)'
                table.add_row(
                    trader_name,
                    str(order.get('symbol', '')),
                    str(order.get('transaction_type', '')),
                    str(order.get('quantity', '')),
                    self._formatter.price_text(order.get('price')),
                    kind,
                    str(order.get('state', '')),
                    self._formatter.time(str(order.get('placed_at', ''))),
                )
