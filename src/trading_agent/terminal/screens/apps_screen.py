"""The Apps page: the packages' web apps, whether they answer, their systemd units, and start, stop, restart and open.

The web page shows an app inside the page; a terminal cannot, so o opens the app in the browser with xdg-open.

Typical usage example:

  app.push_screen(AppsScreen('general'))
"""

import shutil
import subprocess
from typing import Any, ClassVar

from textual import binding
from textual import widgets
from textual import work

from trading_agent.terminal import gateway_client
from trading_agent.terminal.screens import page_screen


class AppsScreen(page_screen.PageScreen):
    """The Apps page."""

    TITLE_TEXT = 'Apps'
    REFRESH_SECONDS = 10.0

    BINDINGS: ClassVar[list[binding.BindingType]] = [
        binding.Binding('o', 'open_app', 'Open in the browser'),
        binding.Binding('s', 'start', 'Start'),
        binding.Binding('t', 'stop', 'Stop'),
        binding.Binding('e', 'restart', 'Restart'),
    ]

    def __init__(self, desk_name: str):
        """Creates the page.

        Args:
            desk_name (str): The desk the chat shows.
        """
        super().__init__(desk_name)
        self._apps: list[dict[str, Any]] = []

    def compose_page(self):
        """Builds the apps table.

        Yields:
            Widget: The table.
        """
        yield widgets.DataTable(id='apps', cursor_type='row')

    def on_mount(self) -> None:
        """Sets up the table, then reads the apps."""
        self.table('apps').add_columns(
            'App', 'What it is', 'Answers', 'Unit', 'Address'
        )
        super().on_mount()

    @work(exclusive=True, group='page')
    async def refresh_page(self) -> None:
        """Reads the apps."""
        try:
            self._apps = await self.app.gateway.apps()
        except gateway_client.GatewayError as error:
            self.problem(error.message)
            return
        table = self.table('apps')
        cursor = table.cursor_row
        table.clear()
        for item in self._apps:
            health = (
                'yes'
                if item.get('healthy')
                else f'no ({item.get("health_detail", "")})'
            )
            unit_state = item.get('unit_state') or {}
            unit = f'{item.get("unit", "")} {unit_state.get("active_state", "")}/{unit_state.get("sub_state", "")}'
            if item.get('unit_error'):
                unit += f' ({item["unit_error"]})'
            table.add_row(
                str(item.get('title') or item.get('package', '')),
                str(item.get('description', ''))[:50],
                health,
                unit,
                str(item.get('url', '')),
                key=str(item.get('package', '')),
            )
        if cursor is not None and cursor < table.row_count:
            table.move_cursor(row=cursor)

    def action_open_app(self) -> None:
        """Opens the highlighted app in the browser."""
        package = self.selected_key('apps')
        for item in self._apps:
            if item.get('package') == package and item.get('url'):
                program = shutil.which('xdg-open')
                if program is None:
                    self.notify(f'Open {item["url"]} in your browser.')
                    return
                subprocess.Popen(
                    [
                        program,
                        str(item['url']),
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                return

    def action_start(self) -> None:
        """Starts the highlighted app's unit."""
        self._act('start')

    def action_stop(self) -> None:
        """Stops the highlighted app's unit."""
        self._act('stop')

    def action_restart(self) -> None:
        """Restarts the highlighted app's unit."""
        self._act('restart')

    def _act(self, action: str) -> None:
        """Runs an action on the highlighted app.

        Args:
            action (str): "start", "stop" or "restart".
        """
        package = self.selected_key('apps')
        if package is not None:
            self._run_action(package, action)

    @work(group='action')
    async def _run_action(self, package: str, action: str) -> None:
        """Asks the gateway to start, stop or restart an app.

        Args:
            package (str): The package.
            action (str): The action.
        """
        try:
            await self.app.gateway.app_action(package, action)
        except gateway_client.GatewayError as error:
            self.problem(error.message)
            return
        self.notify(f'{package}: {action} sent.', timeout=3)
        self.refresh_page()
