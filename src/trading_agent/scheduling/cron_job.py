"""One scheduled job of a trader, and when it next runs.

A job either repeats on a five-field cron schedule in India time ("45 15 * * 1-5" is 15:45 on weekdays) or runs once at a given moment. Two options narrow a repeating schedule: trading_days_only skips weekends and exchange holidays, and market_hours_only keeps only the times when NSE equities are open.

There are three kinds of job:

- an agent job gives the trader a message, as if the user had sent it; with a subagent target, a subagent does the task instead and its report is published;
- a command job runs a shell command in the trader's sandbox, with no model;
- the built-in jobs, the heartbeat and the after-close rollover, come from trading_agent.toml rather than from the jobs file.

Typical usage example:

  job = CronJob.repeating('Morning check', '0 9 * * 1-5', 'Review overnight news', created_by='user')
  moment = job.next_run_after(now, calendar, hours)
"""

import dataclasses
import datetime
import uuid
import zoneinfo
from typing import Any, Self

import croniter

from trading_agent.risk import exchange_hours as exchange_hours_module
from trading_agent.scheduling import market_calendar as market_calendar_module

_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')
_MOST_CANDIDATES = 2000
AGENT = 'agent'
COMMAND = 'command'
TRADER_TARGET = 'trader'
SUBAGENT_TARGET_PREFIX = 'subagent:'


class CronJobError(ValueError):
    """A job's schedule, time or fields are not valid."""


@dataclasses.dataclass(frozen=True)
class CronJob:
    """One scheduled job.

    Attributes:
        job_id: A short identifier, used to delete the job.
        name: A name for people.
        kind: "agent" or "command".
        schedule: The cron expression, or None for a one-off job.
        run_at: The moment of a one-off job, or None for a repeating one.
        text: For an agent job, the message for the trader or the subagent's task; for a command job, the command.
        target: "trader", or "subagent:<name>" for an agent job a subagent does.
        trading_days_only: Whether to skip weekends and exchange holidays.
        market_hours_only: Whether to run only while NSE equities trade.
        deliver_url: An address to POST the result to, or None.
        created_by: "user", "trader" or "built-in".
        created_at: When the job was created, as an ISO 8601 string.
        catch_up: Whether a run missed while the gateway was down is made up once after a restart.
    """

    job_id: str
    name: str
    kind: str
    schedule: str | None
    run_at: str | None
    text: str
    target: str = TRADER_TARGET
    trading_days_only: bool = True
    market_hours_only: bool = False
    deliver_url: str | None = None
    created_by: str = 'user'
    created_at: str = ''
    catch_up: bool = True

    def __post_init__(self) -> None:
        """Checks the fields.

        Raises:
            CronJobError: The job has neither or both of a schedule and a time, an invalid schedule or time, an unknown kind, or an invalid target.
        """
        if (self.schedule is None) == (self.run_at is None):
            raise CronJobError(
                'A job needs either a schedule or a run_at time, not both'
            )
        if self.schedule is not None and not croniter.croniter.is_valid(
            self.schedule
        ):
            raise CronJobError(
                f'{self.schedule!r} is not a valid cron schedule; use five fields: minute hour day month weekday, such as "45 15 * * 1-5"'
            )
        if self.run_at is not None:
            self.run_moment()
        if self.kind not in (AGENT, COMMAND):
            raise CronJobError(
                f'kind must be "agent" or "command", not {self.kind!r}'
            )
        if not self.text.strip():
            raise CronJobError('A job needs a message, task or command')
        is_trader = self.target == TRADER_TARGET
        is_subagent = self.target.startswith(SUBAGENT_TARGET_PREFIX)
        if not is_trader and not is_subagent:
            raise CronJobError(
                f'target must be "trader" or "subagent:<name>", not {self.target!r}'
            )

    @classmethod
    def new(cls, **fields: Any) -> Self:
        """Creates a job with a fresh identifier and creation time.

        Args:
            **fields (Any): The job's other fields.

        Returns:
            CronJob: The job.

        Raises:
            CronJobError: A field is not valid.
        """
        return cls(
            job_id=uuid.uuid4().hex[:8],
            created_at=datetime.datetime.now(_INDIA).isoformat(
                timespec='seconds'
            ),
            **fields,
        )

    @classmethod
    def from_json_dictionary(cls, data: dict[str, Any]) -> Self:
        """Reads a job saved by to_json_dictionary.

        Args:
            data (dict[str, Any]): The saved fields.

        Returns:
            CronJob: The job.

        Raises:
            CronJobError: A field is not valid.
            TypeError: A field is missing or unknown.
        """
        return cls(**data)

    def to_json_dictionary(self) -> dict[str, Any]:
        """Converts the job to a dictionary that json.dumps can write.

        Returns:
            dict[str, Any]: The fields.
        """
        return dataclasses.asdict(self)

    def run_moment(self) -> datetime.datetime:
        """The moment of a one-off job, in India time.

        Returns:
            datetime.datetime: The moment.

        Raises:
            CronJobError: The time is not ISO 8601.
        """
        try:
            moment = datetime.datetime.fromisoformat(str(self.run_at))
        except ValueError as error:
            raise CronJobError(
                f'run_at {self.run_at!r} is not an ISO 8601 time'
            ) from error
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=_INDIA)
        return moment.astimezone(_INDIA)

    def next_run_after(
        self,
        moment: datetime.datetime,
        calendar: market_calendar_module.MarketCalendar,
        hours: exchange_hours_module.ExchangeHours,
    ) -> datetime.datetime | None:
        """The first moment after the given one when the job runs.

        Args:
            moment (datetime.datetime): The moment to count from, not included.
            calendar (market_calendar_module.MarketCalendar): Decides trading days.
            hours (exchange_hours_module.ExchangeHours): Decides market hours.

        Returns:
            datetime.datetime | None: The next run in India time, or None when a one-off job's time has passed or no allowed time is found.
        """
        if self.run_at is not None:
            run_moment = self.run_moment()
            if run_moment > moment:
                return run_moment
            return None
        candidates = croniter.croniter(self.schedule, moment.astimezone(_INDIA))
        for _ in range(_MOST_CANDIDATES):
            candidate = candidates.get_next(datetime.datetime)
            if self._allowed(candidate, calendar, hours):
                return candidate
        return None

    def previous_run_before(
        self,
        moment: datetime.datetime,
        calendar: market_calendar_module.MarketCalendar,
        hours: exchange_hours_module.ExchangeHours,
    ) -> datetime.datetime | None:
        """The last moment before the given one when the job should have run.

        Args:
            moment (datetime.datetime): The moment to count back from.
            calendar (market_calendar_module.MarketCalendar): Decides trading days.
            hours (exchange_hours_module.ExchangeHours): Decides market hours.

        Returns:
            datetime.datetime | None: The previous run in India time, or None for a one-off job still to come or when none is found.
        """
        if self.run_at is not None:
            run_moment = self.run_moment()
            if run_moment <= moment:
                return run_moment
            return None
        candidates = croniter.croniter(self.schedule, moment.astimezone(_INDIA))
        for _ in range(_MOST_CANDIDATES):
            candidate = candidates.get_prev(datetime.datetime)
            if self._allowed(candidate, calendar, hours):
                return candidate
        return None

    def describe(self) -> str:
        """The job in one line, for lists.

        Returns:
            str: Such as "Morning check (agent, 0 9 * * 1-5, trading days only)".
        """
        when = (
            self.schedule
            if self.schedule is not None
            else f'once at {self.run_at}'
        )
        options = []
        if self.trading_days_only and self.schedule is not None:
            options.append('trading days only')
        if self.market_hours_only:
            options.append('market hours only')
        if self.target != TRADER_TARGET:
            options.append(self.target)
        if self.deliver_url:
            options.append(f'delivered to {self.deliver_url}')
        suffix = ''
        if options:
            suffix = ', ' + ', '.join(options)
        return f'{self.name} ({self.kind}, {when}{suffix})'

    def _allowed(
        self,
        candidate: datetime.datetime,
        calendar: market_calendar_module.MarketCalendar,
        hours: exchange_hours_module.ExchangeHours,
    ) -> bool:
        """Says whether a schedule's candidate time passes the job's options.

        Args:
            candidate (datetime.datetime): A time from the cron schedule.
            calendar (market_calendar_module.MarketCalendar): Decides trading days.
            hours (exchange_hours_module.ExchangeHours): Decides market hours.

        Returns:
            bool: True when the job may run then.
        """
        if self.trading_days_only and not calendar.is_trading_day(
            candidate.date()
        ):
            return False
        if self.market_hours_only:
            is_open, _ = hours.is_open(
                'nse', 'nse_equities', candidate, 'exchange_hours'
            )
            return is_open
        return True
