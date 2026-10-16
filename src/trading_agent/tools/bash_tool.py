"""The shallow base class of the four bash tools, which share one desk's terminal.

Typical usage example:

  class BashRunTool(BashTool):
      ...
"""

from trading_agent.tools import bash_session as bash_session_module
from trading_agent.tools import tool


class BashTool(tool.Tool):
    """A tool that works on the desk's sandboxed terminal."""

    def __init__(self, session: bash_session_module.BashSession):
        """Creates the tool.

        Args:
            session (bash_session_module.BashSession): The desk's terminal.
        """
        self._session = session

    def _result_from(
        self,
        outcome: bash_session_module.CommandOutcome,
    ) -> tool.ToolResult:
        """Turns a command's outcome into a tool result.

        Args:
            outcome (bash_session_module.CommandOutcome): What the command produced.

        Returns:
            tool.ToolResult: The output with its exit status; an error result when the command failed or was stopped.
        """
        lines = [
            outcome.output or '(no output)',
        ]
        if outcome.truncated:
            lines.append('[output cut: the rest was too long]')
        if outcome.exit_status is None:
            return tool.ToolResult.error('\n'.join(lines))
        lines.append(f'[exit status {outcome.exit_status}]')
        if outcome.exit_status != 0:
            return tool.ToolResult.error('\n'.join(lines))
        return tool.ToolResult.success('\n'.join(lines))
