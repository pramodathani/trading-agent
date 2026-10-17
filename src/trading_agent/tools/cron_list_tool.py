"""The cron_list tool: lists the desk's scheduled jobs and their next runs.

Typical usage example:

  tool = CronListTool(store, built_in_jobs, calendar, hours)
"""

import datetime
import zoneinfo
from collections.abc import Sequence

from trading_agent.risk import exchange_hours as exchange_hours_module
from trading_agent.scheduling import cron_job as cron_job_module
from trading_agent.scheduling import cron_job_store as cron_job_store_module
from trading_agent.scheduling import market_calendar as market_calendar_module
from trading_agent.tools import tool

_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')


class CronListTool(tool.Tool):
    """Lists the jobs."""

    name = 'cron_list'
    description = "Lists your scheduled jobs, the built-in heartbeat and rollover included, with each job's id and next run. Delete your own jobs with cron_delete; the built-in ones are set by the user in trading_agent.toml."

    def __init__(
        self,
        store: cron_job_store_module.CronJobStore,
        built_in_jobs: Sequence[cron_job_module.CronJob],
        calendar: market_calendar_module.MarketCalendar,
        hours: exchange_hours_module.ExchangeHours,
    ):
        """Creates the tool.

        Args:
            store (cron_job_store_module.CronJobStore): The desk's jobs.
            built_in_jobs (Sequence[cron_job_module.CronJob]): The heartbeat and rollover.
            calendar (market_calendar_module.MarketCalendar): Decides trading days.
            hours (exchange_hours_module.ExchangeHours): Decides market hours.
        """
        self._store = store
        self._built_in_jobs = list(built_in_jobs)
        self._calendar = calendar
        self._hours = hours

    async def run(self, arguments: tool.NoArguments) -> tool.ToolResult:
        """Lists every job with its next run.

        Args:
            arguments (tool.NoArguments): No arguments.

        Returns:
            tool.ToolResult: One line per job.
        """
        del arguments
        now = datetime.datetime.now(_INDIA)
        lines = []
        for job in [*self._built_in_jobs, *self._store.jobs()]:
            next_run = job.next_run_after(now, self._calendar, self._hours)
            when = (
                f'next {next_run:%a %d %b %H:%M}'
                if next_run
                else 'no further runs'
            )
            lines.append(
                f'{job.job_id}: {job.describe()}; {when}; by {job.created_by}'
            )
        return tool.ToolResult.success('\n'.join(lines))
