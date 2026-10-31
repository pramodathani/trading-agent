"""The schedule_wakeup tool: wakes the trader once, later, with a message to itself.

Typical usage example:

  tool = ScheduleWakeupTool(store)
"""

import datetime
import zoneinfo

import pydantic

from trading_agent.scheduling import cron_job as cron_job_module
from trading_agent.scheduling import cron_job_store as cron_job_store_module
from trading_agent.tools import tool

_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')


class ScheduleWakeupArguments(pydantic.BaseModel):
    """The arguments of schedule_wakeup.

    Attributes:
        minutes: Wake up this many minutes from now.
        at: Or wake up at this India time today, as HH:MM; tomorrow when it has passed.
        message: What to tell yourself when you wake, such as what to check.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    minutes: int | None = pydantic.Field(default=None, ge=1, le=60 * 24 * 7)
    at: str | None = pydantic.Field(
        default=None, pattern=r'^([01][0-9]|2[0-3]):[0-5][0-9]$'
    )
    message: str = pydantic.Field(min_length=1)

    @pydantic.model_validator(mode='after')
    def _require_one_time(self) -> ScheduleWakeupArguments:
        """Checks that exactly one of minutes and at is given.

        Returns:
            ScheduleWakeupArguments: These arguments, unchanged.

        Raises:
            ValueError: Both or neither are given.
        """
        if (self.minutes is None) == (self.at is None):
            raise ValueError('Give either minutes or at, not both')
        return self


class ScheduleWakeupTool(tool.Tool):
    """Adds a one-off job that messages the trader."""

    name = 'schedule_wakeup'
    description = 'Wakes you once, later, with a message to yourself: in a number of minutes, or at an India time today (tomorrow if it has passed). Use it to come back to something, such as checking whether a limit order filled by 14:00. It runs even on a holiday; check the market calendar yourself if that matters.'
    arguments_model = ScheduleWakeupArguments

    def __init__(self, store: cron_job_store_module.CronJobStore):
        """Creates the tool.

        Args:
            store (cron_job_store_module.CronJobStore): The trader's jobs.
        """
        self._store = store

    async def run(self, arguments: ScheduleWakeupArguments) -> tool.ToolResult:
        """Stores the one-off job.

        Args:
            arguments (ScheduleWakeupArguments): When, and the message.

        Returns:
            tool.ToolResult: When the trader will wake.
        """
        now = datetime.datetime.now(_INDIA)
        if arguments.minutes is not None:
            moment = now + datetime.timedelta(minutes=arguments.minutes)
        else:
            moment = datetime.datetime.combine(
                now.date(),
                datetime.time.fromisoformat(arguments.at),
                tzinfo=_INDIA,
            )
            if moment <= now:
                moment = moment + datetime.timedelta(days=1)
        job = cron_job_module.CronJob.new(
            name=f'Wake-up: {arguments.message[:40]}',
            kind=cron_job_module.AGENT,
            schedule=None,
            run_at=moment.isoformat(timespec='seconds'),
            text=arguments.message,
            trading_days_only=False,
            created_by='trader',
        )
        self._store.add(job)
        return tool.ToolResult.success(
            f'You will be woken at {moment:%a %d %b %H:%M} India time (job {job.job_id}).'
        )
