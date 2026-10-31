"""Runs every trader's scheduled jobs: the user's, the trader's own, the heartbeat and the after-close rollover.

The scheduler is a loop with no model. When it starts, it makes up once for each run missed while the gateway was down, if the missed run was within the last 24 hours and the job allows it. Then, every 30 seconds or sooner, it starts each job whose next run has come:

- an agent job for the trader joins the trader's queue as a trigger, so it never runs beside one of the trader's turns; the heartbeat is skipped when the trader is busy or has triggers waiting, so heartbeats cannot pile up;
- an agent job for a subagent and a command job run on their own, and their result is published as a cron_result event;
- a job with a delivery address has its result POSTed there, with secrets masked;
- a one-off job is deleted after it starts.

Each run is recorded in the trader's runs.jsonl before it starts, so a crash cannot make a job run twice.

Typical usage example:

  scheduler = CronScheduler(trader_schedules, calendar, hours, event_bus, redactor)
  task = asyncio.create_task(scheduler.run())
"""

import asyncio
import dataclasses
import datetime
import logging
import zoneinfo
from collections.abc import Callable, Coroutine, Mapping
from typing import Any

import httpx

from trading_agent.journal import secret_redactor as secret_redactor_module
from trading_agent.risk import exchange_hours as exchange_hours_module
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trader_runtime as trader_runtime_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.scheduling import (
    command_job_runner as command_job_runner_module,
)
from trading_agent.scheduling import cron_job as cron_job_module
from trading_agent.scheduling import cron_job_store as cron_job_store_module
from trading_agent.scheduling import market_calendar as market_calendar_module
from trading_agent.subagents import subagent_runner as subagent_runner_module

_LOGGER = logging.getLogger(__name__)
_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')
_LONGEST_SLEEP = datetime.timedelta(seconds=30)
_CATCH_UP_WINDOW = datetime.timedelta(hours=24)
_DELIVERY_TIMEOUT_SECONDS = 15.0
HEARTBEAT_JOB_ID = 'heartbeat'
ROLLOVER_JOB_ID = 'rollover'


@dataclasses.dataclass
class TraderSchedule:
    """What the scheduler needs for one trader.

    Attributes:
        trader: The running trader.
        store: Its jobs and run record.
        built_in_jobs: The heartbeat and rollover jobs from trading_agent.toml.
        command_runner: Runs its command jobs.
        subagent_runner: Runs its subagent jobs.
    """

    trader: trader_runtime_module.TraderRuntime
    store: cron_job_store_module.CronJobStore
    built_in_jobs: list[cron_job_module.CronJob]
    command_runner: command_job_runner_module.CommandJobRunner
    subagent_runner: subagent_runner_module.SubagentRunner

    def all_jobs(self) -> list[cron_job_module.CronJob]:
        """The built-in jobs, then the stored ones.

        Returns:
            list[cron_job_module.CronJob]: Every job of the trader.
        """
        return [*self.built_in_jobs, *self.store.jobs()]


class CronScheduler:
    """Starts scheduled jobs on time."""

    def __init__(
        self,
        schedules: Mapping[str, TraderSchedule],
        calendar: market_calendar_module.MarketCalendar,
        hours: exchange_hours_module.ExchangeHours,
        event_bus: event_bus_module.EventBus,
        redactor: secret_redactor_module.SecretRedactor | None = None,
        clock: Callable[[], datetime.datetime] | None = None,
    ):
        """Subscribes to the bus at once, so no result to deliver is missed.

        Args:
            schedules (Mapping[str, TraderSchedule]): Each trader's schedule, keyed by trader name.
            calendar (market_calendar_module.MarketCalendar): Decides trading days.
            hours (exchange_hours_module.ExchangeHours): Decides market hours.
            event_bus (event_bus_module.EventBus): Where runs and results are published, and trader answers are read for delivery.
            redactor (secret_redactor_module.SecretRedactor | None): Masks secrets in delivered results, or None.
            clock (Callable[[], datetime.datetime] | None): Returns the current time; None uses the system clock. Tests replace it.
        """
        self._schedules = schedules
        self._calendar = calendar
        self._hours = hours
        self._event_bus = event_bus
        self._redactor = redactor
        self._clock = clock
        self._started_at = self.now()
        self._pending_deliveries: dict[
            str, tuple[cron_job_module.CronJob, str]
        ] = {}
        self._running: set[asyncio.Task] = set()
        self._subscription = event_bus.subscribe()

    def now(self) -> datetime.datetime:
        """The current time in India.

        Returns:
            datetime.datetime: The time.
        """
        if self._clock is not None:
            return self._clock()
        return datetime.datetime.now(_INDIA)

    async def run(self) -> None:
        """Catches up, then starts due jobs until cancelled."""
        delivery = asyncio.create_task(self._deliver_trader_answers())
        try:
            await self.catch_up()
            while True:
                soonest = await self.tick()
                wait = (soonest - self.now()).total_seconds()
                await asyncio.sleep(max(1.0, wait))
        finally:
            delivery.cancel()
            for task in list(self._running):
                task.cancel()
            self._subscription.close()

    async def catch_up(self) -> list[str]:
        """Starts once each job that missed a run while the gateway was down.

        Returns:
            list[str]: The names of the jobs started.
        """
        started = []
        for schedule in self._schedules.values():
            for job in schedule.all_jobs():
                missed = self._missed_run(schedule, job)
                if missed is not None:
                    await self._start(schedule, job, missed, catching_up=True)
                    started.append(job.name)
        return started

    async def tick(self) -> datetime.datetime:
        """Starts every job whose next run has come.

        Returns:
            datetime.datetime: When to look again: the earliest next run, but no later than 30 seconds from now.
        """
        now = self.now()
        soonest = now + _LONGEST_SLEEP
        for schedule in self._schedules.values():
            for job in schedule.all_jobs():
                due = self._next_run(schedule, job)
                if due is None:
                    continue
                if due <= now:
                    await self._start(schedule, job, due, catching_up=False)
                    due = self._next_run(schedule, job)
                if due is not None and due < soonest:
                    soonest = due
        return soonest

    async def run_now(self, trader_name: str, job_id: str) -> bool:
        """Starts one job at once, as if its time had come.

        Args:
            trader_name (str): The trader.
            job_id (str): The job.

        Returns:
            bool: True when the job was found and started, False when the trader or job is unknown.
        """
        schedule = self._schedules.get(trader_name)
        if schedule is None:
            return False
        for job in schedule.all_jobs():
            if job.job_id == job_id:
                await self._start(schedule, job, self.now(), catching_up=False)
                return True
        return False

    def upcoming(
        self,
        job: cron_job_module.CronJob,
        count: int,
    ) -> list[datetime.datetime]:
        """The next few runs of a job, for lists.

        Args:
            job (cron_job_module.CronJob): The job.
            count (int): How many runs.

        Returns:
            list[datetime.datetime]: The runs, soonest first.
        """
        runs = []
        moment = self.now()
        for _ in range(count):
            moment = job.next_run_after(moment, self._calendar, self._hours)
            if moment is None:
                break
            runs.append(moment)
        return runs

    def _next_run(
        self,
        schedule: TraderSchedule,
        job: cron_job_module.CronJob,
    ) -> datetime.datetime | None:
        """A job's next run, counted from its last run, its creation, or when the scheduler started.

        Args:
            schedule (TraderSchedule): The trader's schedule.
            job (cron_job_module.CronJob): The job.

        Returns:
            datetime.datetime | None: The next run, or None when there is none.
        """
        since = self._started_at
        last = schedule.store.last_run(job.job_id)
        if last is not None and last > since:
            since = last
        created = self._created_at(job)
        if created is not None and created > since:
            since = created
        return job.next_run_after(since, self._calendar, self._hours)

    def _missed_run(
        self,
        schedule: TraderSchedule,
        job: cron_job_module.CronJob,
    ) -> datetime.datetime | None:
        """The run a job missed while the gateway was down, if it should be made up.

        Args:
            schedule (TraderSchedule): The trader's schedule.
            job (cron_job_module.CronJob): The job.

        Returns:
            datetime.datetime | None: The missed run, or None.
        """
        if not job.catch_up:
            return None
        previous = job.previous_run_before(
            self._started_at, self._calendar, self._hours
        )
        if previous is None or self._started_at - previous > _CATCH_UP_WINDOW:
            return None
        created = self._created_at(job)
        if created is not None and created >= previous:
            return None
        last = schedule.store.last_run(job.job_id)
        if last is not None and last >= previous:
            return None
        return previous

    async def _start(
        self,
        schedule: TraderSchedule,
        job: cron_job_module.CronJob,
        moment: datetime.datetime,
        catching_up: bool,
    ) -> None:
        """Starts one run of a job.

        Args:
            schedule (TraderSchedule): The trader's schedule.
            job (cron_job_module.CronJob): The job.
            moment (datetime.datetime): The scheduled moment.
            catching_up (bool): Whether this run makes up for a missed one.
        """
        trader = schedule.trader
        if job.job_id == HEARTBEAT_JOB_ID and (
            trader.state != trader_runtime_module.TraderState.IDLE
            or trader.queued_count
        ):
            schedule.store.record_run(
                job, moment, 'skipped', 'the trader was busy'
            )
            return
        detail = 'catching up a missed run' if catching_up else ''
        schedule.store.record_run(job, moment, 'started', detail)
        if job.run_at is not None:
            schedule.store.delete(job.job_id)
        self._publish(
            event_module.EventKind.CRON_FIRED,
            trader.name,
            {
                'job_id': job.job_id,
                'name': job.name,
                'kind': job.kind,
                'target': job.target,
                'scheduled_for': moment.isoformat(),
                'catching_up': catching_up,
            },
        )
        if job.kind == cron_job_module.COMMAND:
            self._in_background(self._run_command(schedule, job))
        elif job.target == cron_job_module.TRADER_TARGET:
            self._submit_to_trader(schedule, job, catching_up)
        else:
            self._in_background(self._run_subagent(schedule, job))

    def _submit_to_trader(
        self,
        schedule: TraderSchedule,
        job: cron_job_module.CronJob,
        catching_up: bool,
    ) -> None:
        """Puts an agent job's message in the trader's queue.

        Args:
            schedule (TraderSchedule): The trader's schedule.
            job (cron_job_module.CronJob): The job.
            catching_up (bool): Whether this run makes up for a missed one, mentioned in the message.
        """
        source = trigger_module.TriggerSource.CRON
        text = job.text
        if job.job_id == HEARTBEAT_JOB_ID:
            source = trigger_module.TriggerSource.HEARTBEAT
        elif job.created_by != 'built-in':
            late = (
                ' It is running late, because the gateway was down at its time.'
                if catching_up
                else ''
            )
            text = f'[Scheduled job "{job.name}" ({job.job_id}).{late}]\n{job.text}'
        trigger = trigger_module.Trigger.now(source, schedule.trader.name, text)
        if job.deliver_url:
            self._pending_deliveries[trigger.trigger_id] = (
                job,
                job.deliver_url,
            )
        schedule.trader.submit(trigger)

    async def _run_command(
        self,
        schedule: TraderSchedule,
        job: cron_job_module.CronJob,
    ) -> None:
        """Runs a command job and publishes its output.

        Args:
            schedule (TraderSchedule): The trader's schedule.
            job (cron_job_module.CronJob): The job.
        """
        exit_code, output = await schedule.command_runner.run(job.text)
        await self._finish(
            schedule.trader.name, job, f'exit code {exit_code}', output
        )

    async def _run_subagent(
        self,
        schedule: TraderSchedule,
        job: cron_job_module.CronJob,
    ) -> None:
        """Runs a subagent job and publishes its report.

        Args:
            schedule (TraderSchedule): The trader's schedule.
            job (cron_job_module.CronJob): The job.
        """
        name = job.target.removeprefix(cron_job_module.SUBAGENT_TARGET_PREFIX)
        report = await schedule.subagent_runner.run_one(
            subagent_runner_module.SubagentTask(subagent=name, task=job.text)
        )
        await self._finish(
            schedule.trader.name, job, report.outcome, report.text
        )

    async def _finish(
        self,
        trader_name: str,
        job: cron_job_module.CronJob,
        outcome: str,
        text: str,
    ) -> None:
        """Publishes a job's result and delivers it when asked to.

        Args:
            trader_name (str): The trader.
            job (cron_job_module.CronJob): The job.
            outcome (str): How it ended.
            text (str): Its output or report.
        """
        self._publish(
            event_module.EventKind.CRON_RESULT,
            trader_name,
            {
                'job_id': job.job_id,
                'name': job.name,
                'outcome': outcome,
                'text': text,
            },
        )
        if job.deliver_url:
            await self._deliver(trader_name, job, job.deliver_url, text)

    async def _deliver_trader_answers(self) -> None:
        """Delivers the trader's answers to agent jobs that have a delivery address."""
        while True:
            published = await self._subscription.next_event()
            if published.kind != event_module.EventKind.TEXT:
                continue
            pending = self._pending_deliveries.pop(
                published.payload.get('trigger_id', ''),
                None,
            )
            if pending is None:
                continue
            job, url = pending
            await self._deliver(
                published.trader, job, url, published.payload.get('text', '')
            )

    async def _deliver(
        self,
        trader_name: str,
        job: cron_job_module.CronJob,
        url: str,
        text: str,
    ) -> None:
        """POSTs a result as JSON, with secrets masked; a failure is logged.

        Args:
            trader_name (str): The trader.
            job (cron_job_module.CronJob): The job.
            url (str): The address.
            text (str): The result.
        """
        body = {
            'trader': trader_name,
            'job_id': job.job_id,
            'job': job.name,
            'text': text,
            'at': self.now().isoformat(),
        }
        if self._redactor is not None:
            body = self._redactor.redact(body)
        try:
            async with httpx.AsyncClient(
                timeout=_DELIVERY_TIMEOUT_SECONDS
            ) as client:
                response = await client.post(url, json=body)
                response.raise_for_status()
        except httpx.HTTPError as error:
            _LOGGER.warning(
                'Could not deliver job %s to %s: %s', job.name, url, error
            )

    def _in_background(self, coroutine: Coroutine[Any, Any, None]) -> None:
        """Runs a coroutine as a task the scheduler keeps track of.

        Args:
            coroutine (Coroutine[Any, Any, None]): The coroutine.
        """
        task = asyncio.create_task(coroutine)
        self._running.add(task)
        task.add_done_callback(self._running.discard)

    def _created_at(
        self, job: cron_job_module.CronJob
    ) -> datetime.datetime | None:
        """When a job was created.

        Args:
            job (cron_job_module.CronJob): The job.

        Returns:
            datetime.datetime | None: The moment, or None for a built-in job or an unreadable time.
        """
        if not job.created_at:
            return None
        try:
            created = datetime.datetime.fromisoformat(job.created_at)
        except ValueError:
            return None
        if created.tzinfo is None:
            created = created.replace(tzinfo=_INDIA)
        return created

    def _publish(
        self,
        kind: event_module.EventKind,
        trader_name: str,
        payload: dict,
    ) -> None:
        """Publishes an event for a trader.

        Args:
            kind (event_module.EventKind): What happened.
            trader_name (str): The trader.
            payload (dict): The details.
        """
        self._event_bus.publish(
            event_module.Event.now(kind, trader_name, payload)
        )
