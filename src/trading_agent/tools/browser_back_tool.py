"""The browser_back tool: goes back one page.

Typical usage example:

  tool = BrowserBackTool(session)
"""

from trading_agent.tools import browser_tool
from trading_agent.tools import tool


class BrowserBackTool(browser_tool.BrowserTool):
    """Goes back one page in the current tab."""

    name = 'browser_back'
    description = 'Goes back to the previous page in the current tab and returns its snapshot.'

    async def run(self, arguments: tool.NoArguments) -> tool.ToolResult:
        """Goes back.

        Args:
            arguments (tool.NoArguments): No arguments.

        Returns:
            tool.ToolResult: The previous page's snapshot, or an error.
        """
        del arguments
        return await self._text_result(self._session.back())
