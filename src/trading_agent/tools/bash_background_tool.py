"""The bash_background tool: starts a long command and returns at once.

Typical usage example:

  tool = BashBackgroundTool(session)
"""

from trading_agent.tools import bash_command_arguments
from trading_agent.tools import bash_tool
from trading_agent.tools import tool


class BashBackgroundTool(bash_tool.BashTool):
    """Starts a command that keeps running after the call returns."""

    name = 'bash_background'
    description = 'Starts a long-running bash command in the background and returns a job id at once. Check on it later with bash_check. Background jobs stop if the terminal restarts.'
    arguments_model = bash_command_arguments.CommandArguments

    async def run(
        self,
        arguments: bash_command_arguments.CommandArguments,
    ) -> tool.ToolResult:
        """Starts the job.

        Args:
            arguments (bash_command_arguments.CommandArguments): The command.

        Returns:
            tool.ToolResult: The job id.
        """
        job_id = await self._session.run_in_background(arguments.command)
        return tool.ToolResult.success(
            f'Started background job {job_id}. Check it with bash_check.'
        )
