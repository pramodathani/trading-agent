"""The cron_create tool: schedules a repeating job for the trader.

Typical usage example:

  tool = CronCreateTool(store, calendar, hours)
"""

import datetime
import zoneinfo

import pydantic

from trading_agent.risk import exchange_hours as exchange_hours_module
from trading_agent.scheduling import cron_job as cron_job_module
from trading_agent.scheduling import cron_job_store as cron_job_store_module
from trading_agent.scheduling import market_calendar as market_calendar_module
from trading_agent.tools import tool

_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')


class CronCreateArguments(pydantic.BaseModel):
    """The arguments of cron_create.

    Attributes:
        name: A short name for the job.
        schedule: Five cron fields in India time: minute hour day month weekday, such as "30 9 * * 1-5".
        instructions: For an agent job: the message you will receive at each run, or the subagent's task.
        command: For a command job instead: the exact shell command to run, such as "python3 scan.py".
        target: "trader" for yourself, or "subagent:<name>" to have a subagent do it.
        trading_days_only: Whether to skip weekends and exchange holidays.
        market_hours_only: Whether to run only while NSE equities trade.
        deliver_url: An address to POST the result to, or None.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    name: str = pydantic.Field(min_length=1, max_length=80)
    schedule: str = pydantic.Field(min_length=9)
    instructions: str | None = None
    command: str | None = None
    target: str = cron_job_module.TRADER_TARGET
    trading_days_only: bool = True
    market_hours_only: bool = False
    deliver_url: str | None = None

    @pydantic.model_validator(mode='after')
    def _require_instructions_or_command(self) -> CronCreateArguments:
        """Checks that exactly one of instructions and command is given.

        Returns:
            CronCreateArguments: These arguments, unchanged.

        Raises:
            ValueError: Both or neither are given.
        """
        if (self.instructions is None) == (self.command is None):
            raise ValueError(
                'Give instructions for an agent job or command for a command job, not both'
            )
        return self


class CronCreateTool(tool.Tool):
    """Adds a repeating job."""

    name = 'cron_create'
    description = 'Schedules a repeating job on five cron fields in India time (minute hour day month weekday; "*/15 9-15 * * 1-5" is every 15 minutes from 09:00 to 15:45 on weekdays). With instructions, an agent job sends you them as a message at each run, or with target "subagent:<name>" has that subagent do them. With command instead, a command job runs that exact shell command in your sandbox with no model; put only the command there, not a description of it. trading_days_only (on by default) skips weekends and exchange holidays; market_hours_only keeps only times when NSE equities trade. A run missed while the gateway was down is made up once on restart. Answer a scheduled message with exactly NOTHING_TO_DO when nothing needs doing, and no message reaches the user.'
    arguments_model = CronCreateArguments

    def __init__(
        self,
        store: cron_job_store_module.CronJobStore,
        calendar: market_calendar_module.MarketCalendar,
        hours: exchange_hours_module.ExchangeHours,
    ):
        """Creates the tool.

        Args:
            store (cron_job_store_module.CronJobStore): The trader's jobs.
            calendar (market_calendar_module.MarketCalendar): Decides trading days.
            hours (exchange_hours_module.ExchangeHours): Decides market hours.
        """
        self._store = store
        self._calendar = calendar
        self._hours = hours

    async def run(self, arguments: CronCreateArguments) -> tool.ToolResult:
        """Checks and stores the job, and shows its next runs.

        Args:
            arguments (CronCreateArguments): The job.

        Returns:
            tool.ToolResult: The job's id and next three runs, or why it was refused.
        """
        kind = cron_job_module.AGENT
        text = arguments.instructions
        if arguments.command is not None:
            kind = cron_job_module.COMMAND
            text = arguments.command
        try:
            job = cron_job_module.CronJob.new(
                name=arguments.name,
                kind=kind,
                schedule=arguments.schedule.strip(),
                run_at=None,
                text=text,
                target=arguments.target,
                trading_days_only=arguments.trading_days_only,
                market_hours_only=arguments.market_hours_only,
                deliver_url=arguments.deliver_url,
                created_by='trader',
            )
        except cron_job_module.CronJobError as error:
            return tool.ToolResult.error(str(error))
        runs = []
        moment = datetime.datetime.now(_INDIA)
        for _ in range(3):
            moment = job.next_run_after(moment, self._calendar, self._hours)
            if moment is None:
                break
            runs.append(f'{moment:%a %d %b %H:%M}')
        if not runs:
            return tool.ToolResult.error(
                'That schedule never runs with these options; check the fields and the trading-day and market-hours settings.'
            )
        self._store.add(job)
        return tool.ToolResult.success(
            f'Scheduled {job.describe()} as job {job.job_id}. Next runs: {", ".join(runs)}.'
        )
