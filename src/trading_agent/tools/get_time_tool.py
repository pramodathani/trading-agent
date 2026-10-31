"""A tool that tells the model the current date and time in India.

Models do not know the time, and a trader needs it for nearly every decision, so this is the first tool.

Typical usage example:

  result = await GetTimeTool().run(NoArguments())
"""

import datetime
import zoneinfo

from trading_agent.tools import tool

_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')


class GetTimeTool(tool.Tool):
    """Returns the current date, weekday and time in India."""

    name = 'get_time'
    description = 'Returns the current date, weekday and time in India (Asia/Kolkata). Takes no arguments.'
    arguments_model = tool.NoArguments

    async def run(self, arguments: tool.NoArguments) -> tool.ToolResult:
        """Reads the clock.

        Args:
            arguments (tool.NoArguments): No arguments.

        Returns:
            tool.ToolResult: For example "Friday 2026-10-16 10:15:03 IST (UTC+05:30)".
        """
        del arguments
        now = datetime.datetime.now(_INDIA)
        return tool.ToolResult.success(
            now.strftime('%A %Y-%m-%d %H:%M:%S IST (UTC+05:30)')
        )
