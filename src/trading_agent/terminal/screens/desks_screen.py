"""The Desks page: every desk's state, profit and models, with pause, resume, flatten and a way into its chat.

It copies the web page's DesksPage.tsx. Enter on a desk opens its chat. Flatten runs the desk's own flatten_desk tool through the gateway, so it goes through the risk engine and the journal, and it asks for a reason first.

Typical usage example:

  app.push_screen(DesksScreen('general'))
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


class DesksScreen(page_screen.PageScreen):
    """The Desks page."""

    TITLE_TEXT = 'Desks'
    REFRESH_SECONDS = 5.0

    BINDINGS: ClassVar[list[binding.BindingType]] = [
        binding.Binding('p', 'pause_or_resume', 'Pause or resume'),
        binding.Binding('f', 'flatten', 'Flatten'),
    ]

    def __init__(self, desk_name: str):
        """Creates the page.

        Args:
            desk_name (str): The desk the chat shows.
        """
        super().__init__(desk_name)
        self._formatter = formatter.Formatter()
        self._desks: list[dict[str, Any]] = []

    def compose_page(self):
        """Builds the summary line and the desks table.

        Yields:
            Widget: The summary and the table.
        """
        yield widgets.Static('', id='desks-summary', classes='page-summary')
        yield widgets.DataTable(id='desks', cursor_type='row')
        yield widgets.Static('', id='desks-detail', classes='page-detail')

    def on_mount(self) -> None:
        """Sets up the table's columns, then reads the data."""
        self.table('desks').add_columns(
            'Desk',
            'State',
            'Waiting',
            'Today',
            'Model order',
            'Session',
        )
        super().on_mount()

    @work(exclusive=True, group='page')
    async def refresh_page(self) -> None:
        """Reads the desks and the account."""
        gateway = self.app.gateway
        try:
            document = await gateway.desks()
            account = await gateway.account()
        except gateway_client.GatewayError as error:
            self.problem(error.message)
            return
        self._desks = document.get('desks', [])
        positions = len(account.get('positions') or [])
        self.query_one('#desks-summary', widgets.Static).update(
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
        table = self.table('desks')
        cursor = table.cursor_row
        table.clear()
        halts = account.get('halts') or []
        desk_pnl = account.get('desk_pnl') or {}
        for desk in self._desks:
            name = desk.get('name', '')
            state = str(desk.get('state', ''))
            if desk.get('paused'):
                state += ', paused'
            for halt in halts:
                if halt.get('scope') == name:
                    state += ', halted'
            first_models = []
            for line in (desk.get('models') or [])[:2]:
                first_models.append(str(line))
            table.add_row(
                name,
                state,
                str(desk.get('queued', 0)),
                self._formatter.signed_money(desk_pnl.get(name, 0.0)),
                '; '.join(first_models),
                f'{desk.get("session_id") or "—"} ({desk.get("exchanges", 0)})',
                key=name,
            )
        if cursor is not None and cursor < table.row_count:
            table.move_cursor(row=cursor)

    def on_data_table_row_selected(
        self, event: widgets.DataTable.RowSelected
    ) -> None:
        """Opens the chat with the desk chosen with Enter.

        Args:
            event (widgets.DataTable.RowSelected): The choice.
        """
        event.stop()
        self._open_chat(event.row_key.value)

    def _open_chat(self, name: str | None) -> None:
        """Goes back to the chat, showing a desk.

        Args:
            name (str | None): The desk.
        """
        if name is None:
            return
        self.app.pop_screen()
        if self.app.chat is not None:
            self.app.chat.show_desk(name)

    def action_pause_or_resume(self) -> None:
        """Pauses the highlighted desk, or resumes it when paused."""
        name = self.selected_key('desks')
        if name is not None:
            self._pause_or_resume(name)

    @work(group='action')
    async def _pause_or_resume(self, name: str) -> None:
        """Pauses or resumes a desk.

        Args:
            name (str): The desk.
        """
        paused = False
        for desk in self._desks:
            if desk.get('name') == name:
                paused = bool(desk.get('paused'))
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
        """Asks for a reason, then flattens the highlighted desk."""
        name = self.selected_key('desks')
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
                f"Cancel {name}'s open orders and close its positions, through the risk engine. Other desks and your own holdings are not touched.",
                'Flatten',
            ),
            flatten,
        )

    @work(group='action')
    async def _flatten(self, name: str, reason: str) -> None:
        """Flattens a desk and shows the report.

        Args:
            name (str): The desk.
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
        self.query_one('#desks-detail', widgets.Static).update(
            str(report.get('text', ''))
        )
        self.notify(f'Flatten of {name} finished.', severity=severity)
        self.refresh_page()
