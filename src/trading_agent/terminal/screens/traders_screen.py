"""The Traders page: every trader's state, profit and models, with pause, resume, flatten and a way into its chat.

It copies the web page's TradersPage.tsx. Enter on a trader opens its chat. Flatten runs the trader's own flatten_trader tool through the gateway, so it goes through the risk engine and the journal, and it asks for a reason first.

Typical usage example:

  app.push_screen(TradersScreen('general'))
"""

from typing import Any, ClassVar

from textual import binding
from textual import widgets
from textual import work
from textual.content import Content

from trading_agent.terminal import formatter
from trading_agent.terminal import gateway_client
from trading_agent.terminal.screens import page_screen
from trading_agent.terminal.widgets import confirm_dialog


class TradersScreen(page_screen.PageScreen):
    """The Traders page."""

    TITLE_TEXT = 'Traders'
    REFRESH_SECONDS = 5.0

    BINDINGS: ClassVar[list[binding.BindingType]] = [
        binding.Binding('p', 'pause_or_resume', 'Pause or resume'),
        binding.Binding('f', 'flatten', 'Flatten'),
    ]

    def __init__(self, trader_name: str):
        """Creates the page.

        Args:
            trader_name (str): The trader the chat shows.
        """
        super().__init__(trader_name)
        self._formatter = formatter.Formatter()
        self._traders: list[dict[str, Any]] = []

    def compose_page(self):
        """Builds the summary line and the traders table.

        Yields:
            Widget: The summary and the table.
        """
        yield widgets.Static('', id='traders-summary', classes='page-summary')
        yield widgets.DataTable(id='traders', cursor_type='row')
        yield widgets.Static('', id='traders-detail', classes='page-detail')

    def on_mount(self) -> None:
        """Sets up the table's columns, then reads the data."""
        self.table('traders').add_columns(
            'Trader',
            'State',
            'Waiting',
            'Today',
            'Model order',
            'Session',
        )
        super().on_mount()

    @work(exclusive=True, group='page')
    async def refresh_page(self) -> None:
        """Reads the traders and the account."""
        gateway = self.app.gateway
        try:
            document = await gateway.traders()
            account = await gateway.account()
        except gateway_client.GatewayError as error:
            self.problem(error.message)
            return
        self._traders = document.get('traders', [])
        positions = len(account.get('positions') or [])
        self.query_one('#traders-summary', widgets.Static).update(
            Content.from_markup(
                'Balance [b]$balance[/b]   Today $today   This week $week   Open positions [b]$positions[/b]   [dim]$mode[/dim]',
                balance=self._formatter.money(account.get('total_balance')),
                today=self._formatter.signed_money(account.get('day_pnl')),
                week=self._formatter.signed_money(account.get('week_pnl')),
                positions=str(positions),
                mode='LIVE ORDERS'
                if document.get('mode') == 'live'
                else 'DRY RUN',
            )
        )
        table = self.table('traders')
        cursor = table.cursor_row
        table.clear()
        halts = account.get('halts') or []
        trader_pnl = account.get('trader_pnl') or {}
        for trader in self._traders:
            name = trader.get('name', '')
            state = str(trader.get('state', ''))
            if trader.get('paused'):
                state += ', paused'
            for halt in halts:
                if halt.get('scope') == name:
                    state += ', halted'
            first_models = []
            for line in (trader.get('models') or [])[:2]:
                first_models.append(str(line))
            table.add_row(
                name,
                state,
                str(trader.get('queued', 0)),
                self._formatter.signed_money(trader_pnl.get(name, 0.0)),
                '; '.join(first_models),
                f'{trader.get("session_id") or "—"} ({trader.get("exchanges", 0)})',
                key=name,
            )
        if cursor is not None and cursor < table.row_count:
            table.move_cursor(row=cursor)

    def on_data_table_row_selected(
        self, event: widgets.DataTable.RowSelected
    ) -> None:
        """Opens the chat with the trader chosen with Enter.

        Args:
            event (widgets.DataTable.RowSelected): The choice.
        """
        event.stop()
        self._open_chat(event.row_key.value)

    def _open_chat(self, name: str | None) -> None:
        """Goes back to the chat, showing a trader.

        Args:
            name (str | None): The trader.
        """
        if name is None:
            return
        self.app.pop_screen()
        if self.app.chat is not None:
            self.app.chat.show_trader(name)

    def action_pause_or_resume(self) -> None:
        """Pauses the highlighted trader, or resumes it when paused."""
        name = self.selected_key('traders')
        if name is not None:
            self._pause_or_resume(name)

    @work(group='action')
    async def _pause_or_resume(self, name: str) -> None:
        """Pauses or resumes a trader.

        Args:
            name (str): The trader.
        """
        paused = False
        for trader in self._traders:
            if trader.get('name') == name:
                paused = bool(trader.get('paused'))
        try:
            if paused:
                await self.app.gateway.resume(name)
            else:
                await self.app.gateway.pause(name)
        except gateway_client.GatewayError as error:
            self.problem(error.message)
            return
        self.notify(f'{name} {"resumed" if paused else "paused"}.', timeout=3)
        self.refresh_page()

    def action_flatten(self) -> None:
        """Asks for a reason, then flattens the highlighted trader."""
        name = self.selected_key('traders')
        if name is None:
            return

        def flatten(reason: str | None) -> None:
            """Flattens once a reason is given.

            Args:
                reason (str | None): The reason, or None when cancelled.
            """
            if reason is not None:
                self._flatten(name, reason)

        self.app.push_screen(
            confirm_dialog.ConfirmDialog(
                f'Flatten {name}',
                f"Cancel {name}'s open orders and close its positions, through the risk engine. Other traders and your own holdings are not touched.",
                'Flatten',
            ),
            flatten,
        )

    @work(group='action')
    async def _flatten(self, name: str, reason: str) -> None:
        """Flattens a trader and shows the report.

        Args:
            name (str): The trader.
            reason (str): Why, for the journal.
        """
        try:
            report = await self.app.gateway.flatten(name, reason)
        except gateway_client.GatewayError as error:
            self.problem(error.message)
            return
        severity = 'information'
        if report.get('is_error'):
            severity = 'error'
        self.query_one('#traders-detail', widgets.Static).update(
            str(report.get('text', ''))
        )
        self.notify(f'Flatten of {name} finished.', severity=severity)
        self.refresh_page()
