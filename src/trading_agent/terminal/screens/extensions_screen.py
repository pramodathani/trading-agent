"""The Extensions page: subagents, MCP servers and installed packages.

It copies the web page's ExtensionsPage.tsx and, like it, only shows them; packages are installed with `trading-agent packages install`.

Typical usage example:

  app.push_screen(ExtensionsScreen('general'))
"""

from textual import containers
from textual import widgets
from textual import work
from textual.content import Content

from trading_agent.terminal import gateway_client
from trading_agent.terminal.screens import page_screen


class ExtensionsScreen(page_screen.PageScreen):
    """The Extensions page."""

    TITLE_TEXT = 'Extensions'
    REFRESH_SECONDS = 15.0

    def compose_page(self):
        """Builds the three tables.

        Yields:
            Widget: The sections, in a scroll area.
        """
        with containers.VerticalScroll(classes='page-body'):
            yield widgets.Static('[b]Subagents[/b]', classes='page-heading')
            yield widgets.DataTable(
                id='extensions-subagents', cursor_type='row'
            )
            yield widgets.Static('', id='extensions-broken')
            yield widgets.Static('[b]MCP servers[/b]', classes='page-heading')
            yield widgets.DataTable(id='extensions-mcp', cursor_type='row')
            yield widgets.Static(
                '[b]Packages[/b] [dim]install with trading-agent packages install[/dim]',
                classes='page-heading',
            )
            yield widgets.DataTable(id='extensions-packages', cursor_type='row')

    def on_mount(self) -> None:
        """Sets up the tables, then reads the extensions."""
        self.table('extensions-subagents').add_columns(
            'Subagent', 'What it does', 'Models', 'Turns', 'Timeout', 'Tools'
        )
        self.table('extensions-mcp').add_columns(
            'Server', 'State', 'Type', 'Tools', 'Error'
        )
        self.table('extensions-packages').add_columns(
            'Package',
            'Version',
            'What it is',
            'Skills',
            'Agents',
            'MCP',
            'Hooks',
            'App',
        )
        super().on_mount()

    @work(exclusive=True, group='page')
    async def refresh_page(self) -> None:
        """Reads the subagents, servers and packages."""
        gateway = self.app.gateway
        try:
            subagents = await gateway.subagents()
            servers = await gateway.mcp_servers()
            packages = await gateway.packages()
        except gateway_client.GatewayError as error:
            self.problem(error.message)
            return
        table = self.table('extensions-subagents')
        table.clear()
        for subagent in subagents.get('subagents') or []:
            table.add_row(
                str(subagent.get('name', '')),
                str(subagent.get('description', ''))[:60],
                ', '.join(subagent.get('models') or []),
                str(subagent.get('maximum_turns', '')),
                f'{subagent.get("timeout_seconds", "")} s',
                str(len(subagent.get('tools') or [])),
            )
        broken = []
        for item in subagents.get('broken') or []:
            broken.append(
                Content.from_markup(
                    '[$error]$path: $error_text[/]',
                    path=str(item.get('path', '')),
                    error_text=str(item.get('error', '')),
                )
            )
        self.query_one('#extensions-broken', widgets.Static).update(
            Content('\n').join(broken)
        )
        mcp = self.table('extensions-mcp')
        mcp.clear()
        for server in servers.get('servers') or []:
            mcp.add_row(
                str(server.get('name', '')),
                str(server.get('state', '')),
                str(server.get('type', '')),
                str(len(server.get('tools') or [])),
                str(server.get('error', ''))[:60],
            )
        package_table = self.table('extensions-packages')
        package_table.clear()
        for package in packages.get('packages') or []:
            package_table.add_row(
                str(package.get('name', '')),
                str(package.get('version', '')),
                str(package.get('description', ''))[:50],
                str(len(package.get('skills') or [])),
                str(len(package.get('agents') or [])),
                str(len(package.get('mcp_servers') or [])),
                str(len(package.get('hooks') or [])),
                'yes' if package.get('has_app') else 'no',
            )
