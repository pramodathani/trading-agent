"""The Settings page: the standing "always allow" permissions, with revoke, and the configuration file with secrets masked.

It copies the web page's SettingsPage.tsx. The configuration is read-only here, as on the web page.

Typical usage example:

  app.push_screen(SettingsScreen('general'))
"""

import json
from typing import ClassVar

from textual import binding
from textual import containers
from textual import widgets
from textual import work
from textual.content import Content

from trading_agent.terminal import formatter
from trading_agent.terminal import gateway_client
from trading_agent.terminal.screens import page_screen


class SettingsScreen(page_screen.PageScreen):
    """The Settings page."""

    TITLE_TEXT = 'Settings'
    REFRESH_SECONDS = 60.0

    BINDINGS: ClassVar[list[binding.BindingType]] = [
        binding.Binding('delete', 'revoke', 'Revoke permission'),
    ]

    def compose_page(self):
        """Builds the permissions table and the configuration.

        Yields:
            Widget: The sections, in a scroll area.
        """
        with containers.VerticalScroll(classes='page-body'):
            yield widgets.Static(
                '[b]Standing permissions[/b] [dim]tools a desk may call without asking · delete revokes[/dim]',
                classes='page-heading',
            )
            yield widgets.DataTable(id='settings-grants', cursor_type='row')
            yield widgets.Static(
                '[b]Configuration[/b] [dim]trading_agent.toml, secrets masked, read-only[/dim]',
                classes='page-heading',
            )
            yield widgets.Static('', id='settings-configuration')

    def on_mount(self) -> None:
        """Sets up the table, then reads the settings."""
        self.table('settings-grants').add_columns(
            'Desk', 'Tool', 'Allowed since'
        )
        super().on_mount()

    @work(exclusive=True, group='page')
    async def refresh_page(self) -> None:
        """Reads the permissions and the configuration."""
        gateway = self.app.gateway
        try:
            grants = await gateway.permission_grants()
            configuration = await gateway.configuration()
        except gateway_client.GatewayError as error:
            self.problem(error.message)
            return
        clock = formatter.Formatter()
        table = self.table('settings-grants')
        table.clear()
        for grant in grants:
            table.add_row(
                str(grant.get('desk', '')),
                str(grant.get('tool_name', '')),
                clock.day_time(str(grant.get('granted_at', ''))),
                key=f'{grant.get("desk")}|{grant.get("tool_name")}',
            )
        if not grants:
            table.add_row('—', 'none: every tool in [approvals] asks first', '')
        sections = []
        for name, value in configuration.items():
            sections.append(
                Content.from_markup('[b $accent]$name[/]', name=name)
            )
            sections.append(
                Content(json.dumps(value, indent=2, ensure_ascii=False))
            )
        self.query_one('#settings-configuration', widgets.Static).update(
            Content('\n').join(sections)
        )

    def action_revoke(self) -> None:
        """Revokes the highlighted standing permission."""
        key = self.selected_key('settings-grants')
        if key is None or '|' not in key:
            return
        desk, tool_name = key.split('|', 1)
        self._revoke(desk, tool_name)

    @work(group='action')
    async def _revoke(self, desk: str, tool_name: str) -> None:
        """Makes a desk ask again before calling a tool.

        Args:
            desk (str): The desk.
            tool_name (str): The tool.
        """
        try:
            await self.app.gateway.revoke_permission(desk, tool_name)
        except gateway_client.GatewayError as error:
            self.problem(error.message)
            return
        self.notify(f'{desk} will ask again before {tool_name}.', timeout=3)
        self.refresh_page()
