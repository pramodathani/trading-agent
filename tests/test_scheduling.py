"""Tests for the market calendar, cron jobs, the scheduler, the heartbeat and the scheduling tools."""

import asyncio
import datetime
import json
import zoneinfo
from pathlib import Path

import httpx
import pydantic
import pytest

from trading_agent.configuration import agent_configuration
from trading_agent.risk import exchange_hours
from trading_agent.runtime import desk_runtime
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.runtime import turn_runner
from trading_agent.scheduling import built_in_jobs
from trading_agent.scheduling import cron_job
from trading_agent.scheduling import cron_job_store
from trading_agent.scheduling import cron_scheduler
from trading_agent.scheduling import market_calendar
from trading_agent.subagents import subagent_runner
from trading_agent.tools import cron_create_tool
from trading_agent.tools import cron_delete_tool
from trading_agent.tools import schedule_wakeup_tool

_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')
_CALENDAR_YAML = """year: 2026
holidays:
  nse:
    equity:
      - {date: 2026-10-20, closed: all, name: "Dussehra"}
  mcx:
    commodity:
      - {date: 2026-10-20, closed: morning, name: "Dussehra"}
special_sessions:
  - date: 2026-11-08
    name: "Muhurat trading"
    exchanges: [nse, mcx]
    calendars: [equity, commodity]
    opens: "18:00"
    closes: "19:15"
"""


def _moment(
    day: int, hour: int, minute: int, month: int = 10
) -> datetime.datetime:
    """Builds a 2026 India time.

    Args:
        day (int): The day of the month.
        hour (int): The hour.
        minute (int): The minute.
        month (int): The month.

    Returns:
        datetime.datetime: The moment.
    """
    return datetime.datetime(2026, month, day, hour, minute, tzinfo=_INDIA)


def _calendar(tmp_path: Path) -> market_calendar.MarketCalendar:
    """Writes the test calendar and reads it.

    Args:
        tmp_path (Path): A scratch folder.

    Returns:
        market_calendar.MarketCalendar: The calendar.
    """
    folder = tmp_path / 'calendars'
    folder.mkdir(exist_ok=True)
    (folder / '2026.yaml').write_text(_CALENDAR_YAML, encoding='utf-8')
    return market_calendar.MarketCalendar(folder)


class TestMarketCalendar:
    """The calendar and the exchange hours know holidays and special sessions."""

    def test_holiday_half_day_and_special_session(self, tmp_path: Path) -> None:
        """NSE closes for Dussehra, MCX only in the morning, and Muhurat opens a Sunday evening.

        Args:
            tmp_path (Path): A scratch folder.
        """
        calendar = _calendar(tmp_path)
        assert calendar.years == [
            2026,
        ]
        assert not calendar.is_trading_day(datetime.date(2026, 10, 20))
        assert calendar.next_trading_day(
            datetime.date(2026, 10, 19)
        ) == datetime.date(2026, 10, 21)
        assert calendar.is_trading_day(datetime.date(2026, 11, 8))
        hours = exchange_hours.ExchangeHours(calendar)
        nse_holiday = hours.is_open(
            'nse', 'nse_equities', _moment(20, 10, 0), 'exchange_hours'
        )
        assert nse_holiday == (
            False,
            'it is an exchange holiday (Dussehra); the session is 09:15-15:30 India time on weekdays',
        )
        assert not hours.is_open(
            'mcx', 'mcx_commodities', _moment(20, 10, 0), 'exchange_hours'
        )[0]
        assert hours.is_open(
            'mcx', 'mcx_commodities', _moment(20, 18, 0), 'exchange_hours'
        )[0]
        assert hours.is_open(
            'nse', 'nse_equities', _moment(8, 18, 30, 11), 'exchange_hours'
        )[0]
        assert not hours.is_open(
            'nse', 'nse_equities', _moment(8, 10, 0, 11), 'exchange_hours'
        )[0]

    def test_missing_folder_knows_weekends_only(self, tmp_path: Path) -> None:
        """Without files every weekday trades.

        Args:
            tmp_path (Path): A scratch folder.
        """
        calendar = market_calendar.MarketCalendar(tmp_path / 'absent')
        assert calendar.years == []
        assert calendar.is_trading_day(datetime.date(2026, 10, 20))
        assert not calendar.is_trading_day(datetime.date(2026, 10, 18))


class TestCronJob:
    """Jobs check their fields and find their runs."""

    def test_trading_days_and_market_hours_shape_the_runs(
        self, tmp_path: Path
    ) -> None:
        """A 15:45 job skips Dussehra; a five-minute heartbeat jumps from Monday's close to Wednesday's open.

        Args:
            tmp_path (Path): A scratch folder.
        """
        calendar = _calendar(tmp_path)
        hours = exchange_hours.ExchangeHours(calendar)
        rollover, heartbeat = built_in_jobs.BuiltInJobs().jobs(5, '15:45')
        assert rollover.next_run_after(
            _moment(19, 16, 0), calendar, hours
        ) == _moment(21, 15, 45)
        assert heartbeat.next_run_after(
            _moment(19, 15, 26), calendar, hours
        ) == _moment(21, 9, 15)
        assert heartbeat.previous_run_before(
            _moment(21, 9, 0), calendar, hours
        ) == _moment(19, 15, 25)
        assert built_in_jobs.BuiltInJobs().jobs(None, '15:45') == [
            rollover,
        ]

    def test_invalid_jobs_are_refused(self) -> None:
        """A bad schedule, both a schedule and a time, and a bad target are errors."""
        with pytest.raises(
            cron_job.CronJobError, match='not a valid cron schedule'
        ):
            cron_job.CronJob.new(
                name='x',
                kind='agent',
                schedule='61 * * * *',
                run_at=None,
                text='go',
            )
        with pytest.raises(cron_job.CronJobError, match='not both'):
            cron_job.CronJob.new(
                name='x',
                kind='agent',
                schedule='0 9 * * *',
                run_at='2026-10-19T09:00:00+05:30',
                text='go',
            )
        with pytest.raises(cron_job.CronJobError, match='target'):
            cron_job.CronJob.new(
                name='x',
                kind='agent',
                schedule='0 9 * * *',
                run_at=None,
                text='go',
                target='nobody',
            )


class _FakeDesk:
    """Stands in for a running desk.

    Attributes:
        name: The desk's name.
        state: Its state.
        queued_count: How many triggers wait.
        submitted: The triggers it received.
    """

    def __init__(self):
        """Creates an idle desk."""
        self.name = 'main'
        self.state = desk_runtime.DeskState.IDLE
        self.queued_count = 0
        self.submitted = []

    def submit(self, trigger: trigger_module.Trigger) -> None:
        """Records a trigger.

        Args:
            trigger (trigger_module.Trigger): The trigger.
        """
        self.submitted.append(trigger)


class _FakeCommandRunner:
    """Stands in for the command runner.

    Attributes:
        commands: The commands it ran.
    """

    def __init__(self):
        """Creates the runner."""
        self.commands = []

    async def run(self, command: str) -> tuple[int, str]:
        """Records the command.

        Args:
            command (str): The command.

        Returns:
            tuple[int, str]: Exit code 0 and fixed output.
        """
        self.commands.append(command)
        return 0, 'scan done'


class _FakeSubagentRunner:
    """Stands in for the subagent runner."""

    async def run_one(
        self, task: subagent_runner.SubagentTask
    ) -> subagent_runner.SubagentReport:
        """Answers at once.

        Args:
            task (subagent_runner.SubagentTask): The task.

        Returns:
            subagent_runner.SubagentReport: A report naming the task.
        """
        return subagent_runner.SubagentReport(
            subagent=task.subagent,
            outcome='answered',
            text=f'report on {task.task}',
            backend_name='qwen',
            seconds=1.0,
            notes=(),
        )


class _Clock:
    """A clock the test sets.

    Attributes:
        now: The time it reports.
    """

    def __init__(self, now: datetime.datetime):
        """Sets the clock.

        Args:
            now (datetime.datetime): The first time.
        """
        self.now = now

    def __call__(self) -> datetime.datetime:
        """Reads the clock.

        Returns:
            datetime.datetime: The time.
        """
        return self.now


class _Setup:
    """A scheduler over one fake desk.

    Attributes:
        clock: The scheduler's clock.
        desk: The fake desk.
        store: The desk's job store.
        commands: The fake command runner.
        event_bus: The bus.
        scheduler: The scheduler.
    """

    def __init__(
        self,
        tmp_path: Path,
        start: datetime.datetime,
        heartbeat_minutes: int | None = None,
    ):
        """Builds the scheduler.

        Args:
            tmp_path (Path): A scratch folder.
            start (datetime.datetime): When the scheduler starts.
            heartbeat_minutes (int | None): The heartbeat setting.
        """
        calendar = _calendar(tmp_path)
        self.clock = _Clock(start)
        self.desk = _FakeDesk()
        self.store = cron_job_store.CronJobStore(tmp_path / 'cron')
        self.commands = _FakeCommandRunner()
        self.event_bus = event_bus_module.EventBus()
        schedule = cron_scheduler.DeskSchedule(
            desk=self.desk,
            store=self.store,
            built_in_jobs=built_in_jobs.BuiltInJobs().jobs(
                heartbeat_minutes, '15:45'
            ),
            command_runner=self.commands,
            subagent_runner=_FakeSubagentRunner(),
        )
        self.scheduler = cron_scheduler.CronScheduler(
            {
                'main': schedule,
            },
            calendar,
            exchange_hours.ExchangeHours(calendar),
            self.event_bus,
            clock=self.clock,
        )

    def job(self, **fields: object) -> cron_job.CronJob:
        """Stores a job created a day before the scheduler started.

        Args:
            **fields (object): The job's fields.

        Returns:
            cron_job.CronJob: The job.
        """
        job = cron_job.CronJob(
            job_id=str(fields.pop('job_id', 'job1')),
            created_at=(
                self.clock.now - datetime.timedelta(days=1)
            ).isoformat(),
            **fields,
        )
        self.store.add(job)
        return job


class TestCronScheduler:
    """The scheduler starts jobs on time, catches up once, and skips a busy heartbeat."""

    def test_agent_job_runs_on_time_once(self, tmp_path: Path) -> None:
        """A 09:30 job reaches the desk at 09:30, labelled, and not again at 09:31.

        Args:
            tmp_path (Path): A scratch folder.
        """
        setup = _Setup(tmp_path, _moment(19, 9, 0))
        setup.job(
            name='Open check',
            kind='agent',
            schedule='30 9 * * *',
            run_at=None,
            text='Check the open.',
        )

        async def scenario() -> None:
            """Ticks at 09:29, 09:30 and 09:31."""
            for minute in (29, 30, 31):
                setup.clock.now = _moment(19, 9, minute)
                await setup.scheduler.tick()

        asyncio.run(scenario())
        assert len(setup.desk.submitted) == 1
        trigger = setup.desk.submitted[0]
        assert trigger.source == trigger_module.TriggerSource.CRON
        assert (
            trigger.text
            == '[Scheduled job "Open check" (job1).]\nCheck the open.'
        )
        assert setup.store.last_run('job1') == _moment(19, 9, 30)

    def test_missed_run_is_made_up_once_and_heartbeat_is_not(
        self, tmp_path: Path
    ) -> None:
        """Down at 09:30, started at 10:00: the job catches up once; the heartbeat does not.

        Args:
            tmp_path (Path): A scratch folder.
        """
        setup = _Setup(tmp_path, _moment(19, 10, 0), heartbeat_minutes=15)
        setup.job(
            name='Open check',
            kind='agent',
            schedule='30 9 * * *',
            run_at=None,
            text='Check.',
        )

        async def scenario() -> list[str]:
            """Catches up twice.

            Returns:
                list[str]: The names started by the first catch-up.
            """
            first = await setup.scheduler.catch_up()
            await setup.scheduler.catch_up()
            return first

        assert asyncio.run(scenario()) == [
            'Open check',
        ]
        assert 'running late' in setup.desk.submitted[0].text
        assert len(setup.desk.submitted) == 1

    def test_heartbeat_waits_for_an_idle_desk(self, tmp_path: Path) -> None:
        """A heartbeat on a busy desk is skipped and recorded; the next one on an idle desk runs.

        Args:
            tmp_path (Path): A scratch folder.
        """
        setup = _Setup(tmp_path, _moment(19, 10, 1), heartbeat_minutes=15)
        setup.desk.state = desk_runtime.DeskState.BUSY

        async def scenario() -> None:
            """Ticks at 10:15 busy and 10:30 idle."""
            setup.clock.now = _moment(19, 10, 15)
            await setup.scheduler.tick()
            setup.desk.state = desk_runtime.DeskState.IDLE
            setup.clock.now = _moment(19, 10, 30)
            await setup.scheduler.tick()

        asyncio.run(scenario())
        assert len(setup.desk.submitted) == 1
        assert (
            setup.desk.submitted[0].source
            == trigger_module.TriggerSource.HEARTBEAT
        )
        runs = (
            (tmp_path / 'cron' / 'runs.jsonl')
            .read_text(encoding='utf-8')
            .splitlines()
        )
        assert json.loads(runs[0])['outcome'] == 'skipped'

    def test_one_off_command_and_subagent_jobs(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A one-off job is deleted after it runs; command and subagent results are published and delivered.

        Args:
            tmp_path (Path): A scratch folder.
            monkeypatch (pytest.MonkeyPatch): Routes delivery to a fake server.
        """
        delivered = []

        def handler(request: httpx.Request) -> httpx.Response:
            """Records a delivery.

            Args:
                request (httpx.Request): The POST.

            Returns:
                httpx.Response: A 200 answer.
            """
            delivered.append(json.loads(request.content))
            return httpx.Response(200)

        real_client = httpx.AsyncClient
        monkeypatch.setattr(
            cron_scheduler.httpx,
            'AsyncClient',
            lambda **options: real_client(
                transport=httpx.MockTransport(handler), **options
            ),
        )
        setup = _Setup(tmp_path, _moment(19, 9, 0))
        setup.job(
            job_id='once',
            name='Wake',
            kind='agent',
            schedule=None,
            run_at=_moment(19, 9, 5).isoformat(),
            text='Wake up.',
            trading_days_only=False,
        )
        setup.job(
            job_id='scan',
            name='Scan',
            kind='command',
            schedule='5 9 * * *',
            run_at=None,
            text='python3 scan.py',
            deliver_url='https://example.com/hook',
        )
        setup.job(
            job_id='news',
            name='News',
            kind='agent',
            schedule='5 9 * * *',
            run_at=None,
            text='INFY news',
            target='subagent:news_reader',
        )
        subscription = setup.event_bus.subscribe()

        async def scenario() -> list[event_module.Event]:
            """Ticks at 09:05 and lets the background tasks finish.

            Returns:
                list[event_module.Event]: The cron_result events.
            """
            setup.clock.now = _moment(19, 9, 5)
            await setup.scheduler.tick()
            await asyncio.sleep(0.05)
            results = []
            while True:
                try:
                    published = await asyncio.wait_for(
                        subscription.next_event(), 0.01
                    )
                except TimeoutError:
                    return results
                if published.kind == event_module.EventKind.CRON_RESULT:
                    results.append(published)

        results = asyncio.run(scenario())
        assert [job.job_id for job in setup.store.jobs()] == [
            'scan',
            'news',
        ]
        assert setup.desk.submitted[0].text.endswith('Wake up.')
        assert setup.commands.commands == [
            'python3 scan.py',
        ]
        texts = sorted(result.payload['text'] for result in results)
        assert texts == [
            'report on INFY news',
            'scan done',
        ]
        assert delivered[0]['job'] == 'Scan'
        assert delivered[0]['text'] == 'scan done'


class _ReplyRunner(turn_runner.TurnRunner):
    """A turn runner that always answers NOTHING_TO_DO."""

    async def run_turn(
        self, trigger: trigger_module.Trigger
    ) -> turn_runner.TurnResult:
        """Answers NOTHING_TO_DO.

        Args:
            trigger (trigger_module.Trigger): The trigger.

        Returns:
            turn_runner.TurnResult: The answer.
        """
        del trigger
        return turn_runner.TurnResult(text='NOTHING_TO_DO')


class TestHeartbeatAnswers:
    """NOTHING_TO_DO is silent only for heartbeats and scheduled jobs."""

    def test_silent_flag(self) -> None:
        """A heartbeat answered NOTHING_TO_DO is silent; the same answer to the user is not."""
        event_bus = event_bus_module.EventBus()
        desk = desk_runtime.DeskRuntime(
            agent_configuration.DeskConfiguration(name='main'),
            event_bus,
            _ReplyRunner(),
        )
        subscription = event_bus.subscribe()

        async def scenario() -> list[bool]:
            """Runs a heartbeat and a user message through the desk.

            Returns:
                list[bool]: The silent flag of each text event.
            """
            task = asyncio.create_task(desk.run())
            for source in (
                trigger_module.TriggerSource.HEARTBEAT,
                trigger_module.TriggerSource.USER_MESSAGE,
            ):
                desk.submit(trigger_module.Trigger.now(source, 'main', 'go'))
            flags = []
            while len(flags) < 2:
                published = await subscription.next_event()
                if published.kind == event_module.EventKind.TEXT:
                    flags.append(published.payload['silent'])
            task.cancel()
            return flags

        assert asyncio.run(scenario()) == [
            True,
            False,
        ]


class TestSchedulingTools:
    """The desk's scheduling tools check what they are given."""

    def test_create_wakeup_and_delete(self, tmp_path: Path) -> None:
        """A bad schedule is refused, a good one shows its runs, a wake-up needs one time, and built-ins cannot be deleted.

        Args:
            tmp_path (Path): A scratch folder.
        """
        calendar = _calendar(tmp_path)
        store = cron_job_store.CronJobStore(tmp_path / 'cron')
        create = cron_create_tool.CronCreateTool(
            store, calendar, exchange_hours.ExchangeHours(calendar)
        )
        bad = asyncio.run(
            create.run(
                cron_create_tool.CronCreateArguments(
                    name='x', schedule='99 * * * * *', instructions='go'
                )
            )
        )
        assert bad.is_error
        good = asyncio.run(
            create.run(
                cron_create_tool.CronCreateArguments(
                    name='Close review',
                    schedule='0 16 * * 1-5',
                    instructions='Review the day.',
                )
            )
        )
        assert good.text.startswith(
            'Scheduled Close review (agent, 0 16 * * 1-5, trading days only) as job '
        )
        assert 'Next runs:' in good.text
        job_id = store.jobs()[0].job_id
        with pytest.raises(pydantic.ValidationError):
            cron_create_tool.CronCreateArguments(
                name='x', schedule='0 9 * * *', instructions='a', command='b'
            )
        command = asyncio.run(
            create.run(
                cron_create_tool.CronCreateArguments(
                    name='Clock',
                    schedule='* * * * *',
                    command='date',
                    trading_days_only=False,
                )
            )
        )
        assert '(command, * * * * *)' in command.text
        store.delete(store.jobs()[1].job_id)
        with pytest.raises(pydantic.ValidationError):
            schedule_wakeup_tool.ScheduleWakeupArguments(
                minutes=5, at='14:00', message='x'
            )
        wakeup = schedule_wakeup_tool.ScheduleWakeupTool(store)
        asyncio.run(
            wakeup.run(
                schedule_wakeup_tool.ScheduleWakeupArguments(
                    minutes=30, message='Check the fill.'
                )
            )
        )
        assert store.jobs()[1].run_at is not None
        delete = cron_delete_tool.CronDeleteTool(store)
        refused = asyncio.run(
            delete.run(cron_delete_tool.CronDeleteArguments(job_id='rollover'))
        )
        assert refused.is_error
        deleted = asyncio.run(
            delete.run(cron_delete_tool.CronDeleteArguments(job_id=job_id))
        )
        assert deleted.text.startswith('Deleted Close review')
        assert len(store.jobs()) == 1
