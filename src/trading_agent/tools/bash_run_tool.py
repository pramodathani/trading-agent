"""The bash_run tool: runs one command in the trader's terminal and waits for it.

Typical usage example:

  tool = BashRunTool(session)
"""

from trading_agent.tools import bash_command_arguments
from trading_agent.tools import bash_session as bash_session_module
from trading_agent.tools import bash_tool
from trading_agent.tools import tool

_TIMEOUT_MARGIN_SECONDS = 15.0


class BashRunTool(bash_tool.BashTool):
    """Runs one command and returns its output."""

    name = 'bash_run'
    description = 'Runs a bash command in your own sandboxed terminal and returns its output. The current folder and variables carry over between commands. Everything is read-only except your scratch folder (the starting folder, also $HOME) and /tmp. The internet is reachable. Commands get no keyboard input. For anything that may take longer than about two minutes, use bash_background.'
    arguments_model = bash_command_arguments.CommandArguments

    def __init__(self, session: bash_session_module.BashSession):
        """Creates the tool, with a time limit just above the terminal's own.

        Args:
            session (bash_session_module.BashSession): The trader's terminal.
        """
        super().__init__(session)
        self.timeout_seconds = session.timeout_seconds + _TIMEOUT_MARGIN_SECONDS

    async def run(
        self,
        arguments: bash_command_arguments.CommandArguments,
    ) -> tool.ToolResult:
        """Runs the command.

        Args:
            arguments (bash_command_arguments.CommandArguments): The command.

        Returns:
            tool.ToolResult: Its output and exit status.
        """
        return self._result_from(await self._session.run(arguments.command))

    async def close(self) -> None:
        """Stops the terminal when the trader stops."""
        await self._session.close()
