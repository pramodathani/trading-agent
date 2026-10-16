"""The browser_snapshot tool: lists the current page's numbered elements and text again.

Typical usage example:

  tool = BrowserSnapshotTool(session)
"""

from trading_agent.tools import browser_tool
from trading_agent.tools import tool


class BrowserSnapshotTool(browser_tool.BrowserTool):
    """Takes a fresh snapshot of the current page."""

    name = 'browser_snapshot'
    description = 'Returns a fresh snapshot of the current page: its title, numbered clickable elements and visible text. Take one after the page changes, because element numbers change with it.'

    async def run(self, arguments: tool.NoArguments) -> tool.ToolResult:
        """Takes the snapshot.

        Args:
            arguments (tool.NoArguments): No arguments.

        Returns:
            tool.ToolResult: The snapshot, or an error.
        """
        del arguments
        return await self._text_result(self._session.snapshot())
