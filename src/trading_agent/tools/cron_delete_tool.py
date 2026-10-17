"""The cron_delete tool: removes one of the desk's scheduled jobs.

Typical usage example:

  tool = CronDeleteTool(store)
"""

import pydantic

from trading_agent.scheduling import cron_job_store as cron_job_store_module
from trading_agent.tools import tool


class CronDeleteArguments(pydantic.BaseModel):
    """The arguments of cron_delete.

    Attributes:
        job_id: The job's id, from cron_list.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    job_id: str = pydantic.Field(min_length=1)


class CronDeleteTool(tool.Tool):
    """Deletes a job."""

    name = 'cron_delete'
    description = 'Deletes one scheduled job by its id from cron_list. The built-in heartbeat and rollover cannot be deleted; the user sets them in trading_agent.toml.'
    arguments_model = CronDeleteArguments

    def __init__(self, store: cron_job_store_module.CronJobStore):
        """Creates the tool.

        Args:
            store (cron_job_store_module.CronJobStore): The desk's jobs.
        """
        self._store = store

    async def run(self, arguments: CronDeleteArguments) -> tool.ToolResult:
        """Deletes the job.

        Args:
            arguments (CronDeleteArguments): The job's id.

        Returns:
            tool.ToolResult: A confirmation, or why nothing was deleted.
        """
        if arguments.job_id in ('heartbeat', 'rollover'):
            return tool.ToolResult.error(
                f'{arguments.job_id} is built in; the user sets it in trading_agent.toml.'
            )
        removed = self._store.delete(arguments.job_id)
        if removed is None:
            return tool.ToolResult.error(
                f'No job with id {arguments.job_id}; see cron_list.'
            )
        self._store.forget_run(arguments.job_id)
        return tool.ToolResult.success(f'Deleted {removed.describe()}.')
