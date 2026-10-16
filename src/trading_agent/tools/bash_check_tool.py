"""The bash_check tool: reports on a background job.

Typical usage example:

  tool = BashCheckTool(session)
"""

import pydantic

from trading_agent.tools import bash_tool
from trading_agent.tools import tool


class JobArguments(pydantic.BaseModel):
    """The arguments of bash_check.

    Attributes:
        job_id: The identifier bash_background returned.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    job_id: str = pydantic.Field(pattern=r'^[0-9a-f]{8}$')


class BashCheckTool(bash_tool.BashTool):
    """Says whether a background job is still running."""

    name = 'bash_check'
    description = 'Says whether a background job from bash_background is still running, and shows the end of its output.'
    arguments_model = JobArguments

    async def run(self, arguments: JobArguments) -> tool.ToolResult:
        """Checks the job.

        Args:
            arguments (JobArguments): The job id.

        Returns:
            tool.ToolResult: "running" or "finished", then the end of the job's output.
        """
        outcome = await self._session.check_background(arguments.job_id)
        return self._result_from(outcome)
