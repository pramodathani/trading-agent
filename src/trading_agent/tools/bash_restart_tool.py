"""The bash_restart tool: gives the desk a fresh terminal.

Typical usage example:

  tool = BashRestartTool(session)
"""

from trading_agent.tools import bash_tool
from trading_agent.tools import tool


class BashRestartTool(bash_tool.BashTool):
    """Restarts the desk's terminal."""

    name = 'bash_restart'
    description = 'Restarts your terminal, which resets the current folder and variables and stops background jobs. Use it when the terminal is stuck or in a confusing state.'

    async def run(self, arguments: tool.NoArguments) -> tool.ToolResult:
        """Restarts the terminal.

        Args:
            arguments (tool.NoArguments): No arguments.

        Returns:
            tool.ToolResult: A confirmation.
        """
        del arguments
        await self._session.restart()
        return tool.ToolResult.success('The terminal was restarted.')
