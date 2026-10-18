"""The side panel's Tools card: the desk's own tools and the MCP servers with their tools.

Typical usage example:

  card = ToolsCard()
  card.show(tool_names, servers)
"""

from typing import Any

from textual import widgets
from textual.content import Content

from trading_agent.terminal.widgets import side_card


class ToolsCard(side_card.SideCard):
    """The Tools card, with the two lists folded inside it."""

    def __init__(self, collapsed: bool = False):
        """Creates the card.

        Args:
            collapsed (bool): Whether it starts folded.
        """
        self._tool_list = widgets.Static('', classes='side-list')
        self._server_list = widgets.Static('', classes='side-list')
        self._tools_fold = widgets.Collapsible(
            self._tool_list, title='Desk tools', collapsed=True
        )
        self._servers_fold = widgets.Collapsible(
            self._server_list, title='MCP servers', collapsed=True
        )
        super().__init__(
            'tools',
            'Tools',
            self._tools_fold,
            self._servers_fold,
            collapsed=collapsed,
        )

    def show(
        self,
        tools: list[str],
        servers: list[dict[str, Any]] | None,
    ) -> None:
        """Shows the tools.

        Args:
            tools (list[str]): The desk's tool names.
            servers (list[dict[str, Any]] | None): The MCP servers, or None when not known.
        """
        server_tools = 0
        for server in servers or []:
            server_tools += len(server.get('tools') or [])
        self.show_aside(str(len(tools) + server_tools))
        self.show_body('')
        self._tools_fold.title = f'Desk tools · {len(tools)}'
        self._tool_list.update(Content('\n'.join(sorted(tools))))
        if servers is None:
            self._servers_fold.title = 'MCP servers · —'
            self._server_list.update('')
            return
        self._servers_fold.title = f'MCP servers · {len(servers)}'
        if not servers:
            self._server_list.update(self.note('None configured'))
            return
        lines = []
        for server in servers:
            dot = '[$error]●[/]'
            if server.get('state') == 'ready':
                dot = '[$success]●[/]'
            count = len(server.get('tools') or [])
            lines.append(
                Content.from_markup(
                    f'{dot} $name [dim]$count[/dim]',
                    name=str(server.get('name', '')),
                    count=f'{count} tool' if count == 1 else f'{count} tools',
                )
            )
        self._server_list.update(Content('\n').join(lines))
