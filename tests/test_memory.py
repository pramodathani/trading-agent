"""Tests for sessions, the daily rollover, notes, session search and checkpoints."""

import asyncio
import datetime
import io
import json
import zoneinfo
from pathlib import Path
from typing import Any

import pydantic
import pytest

from trading_agent.backends import backend
from trading_agent.backends import model_router
from trading_agent.client import checkpoint_commands
from trading_agent.memory import checkpoints as checkpoints_module
from trading_agent.memory import session_keeper as session_keeper_module
from trading_agent.memory import session_search
from trading_agent.memory import session_store as session_store_module
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.runtime import turn_runner
from trading_agent.tools import add_note_tool
from trading_agent.tools import path_policy
from trading_agent.tools import search_sessions_tool
from trading_agent.tools import write_file_tool

_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')
_MONDAY = datetime.date(2026, 10, 19)
_TUESDAY = datetime.date(2026, 10, 20)


class _Calendar:
    """A date source the test moves forward by hand.

    Attributes:
        today: The date it reports.
    """

    def __init__(self, today: datetime.date):
        """Starts the calendar on a date.

        Args:
            today (datetime.date): The first date it reports.
        """
        self.today = today

    def __call__(self) -> datetime.date:
        """Reads the calendar.

        Returns:
            datetime.date: The current date.
        """
        return self.today


class _Runner(turn_runner.TurnRunner):
    """A turn runner that records what it was sent and can pretend to resume.

    Attributes:
        name: Used in the answers.
        can_resume: Whether restore_state succeeds, as Claude's does.
        available: Whether turns succeed.
        received_texts: The trigger texts it was given.
        restored_state: What restore_state was given, or None.
        answer: The text it answers with, or None for "<name> answered".
    """

    def __init__(self, name: str, can_resume: bool):
        """Creates the runner.

        Args:
            name (str): Used in the answers.
            can_resume (bool): Whether restore_state succeeds.
        """
        self.name = name
        self.can_resume = can_resume
        self.available = True
        self.received_texts = []
        self.restored_state = None
        self.answer = None

    async def run_turn(
        self,
        trigger: trigger_module.Trigger,
    ) -> turn_runner.TurnResult:
        """Answers, or fails when unavailable.

        Args:
            trigger (trigger_module.Trigger): The turn's trigger.

        Returns:
            turn_runner.TurnResult: The answer.

        Raises:
            backend.BackendUnavailableError: When unavailable.
        """
        self.received_texts.append(trigger.text)
        if not self.available:
            raise backend.BackendUnavailableError(f'{self.name} is down')
        return turn_runner.TurnResult(
            text=self.answer or f'{self.name} answered'
        )

    def saved_state(self) -> dict[str, Any] | None:
        """Saves a fake session id when the runner can resume.

        Returns:
            dict[str, Any] | None: The state, or None.
        """
        if not self.can_resume:
            return None
        return {
            'session_id': f'{self.name}-session',
        }

    async def restore_state(self, state: dict[str, Any]) -> bool:
        """Records the state and resumes when the runner can.

        Args:
            state (dict[str, Any]): The saved state.

        Returns:
            bool: Whether it resumed.
        """
        self.restored_state = state
        return self.can_resume


def _trigger(text: str) -> trigger_module.Trigger:
    """Builds a user-message trigger.

    Args:
        text (str): Its text.

    Returns:
        trigger_module.Trigger: The trigger.
    """
    return trigger_module.Trigger.now(
        trigger_module.TriggerSource.USER_MESSAGE,
        'main',
        text,
    )


class _Desk:
    """A router with a resuming and a forgetting backend, over one sessions folder.

    Attributes:
        claude: The runner that can resume.
        gemma: The runner that forgets on restart.
        calendar: The store's date source.
        store: The session store.
        event_bus: The bus.
        router: The router.
        keeper: The session keeper.
    """

    def __init__(self, directory: Path, calendar: _Calendar):
        """Builds the desk's memory parts.

        Args:
            directory (Path): The sessions folder.
            calendar (_Calendar): The date source.
        """
        self.claude = _Runner('claude', can_resume=True)
        self.gemma = _Runner('gemma', can_resume=False)
        self.calendar = calendar
        self.store = session_store_module.SessionStore(directory, calendar)
        self.event_bus = event_bus_module.EventBus()
        self.router = model_router.ModelRouter(
            'main',
            [
                model_router.BackendRoute('claude', self.claude),
                model_router.BackendRoute('gemma', self.gemma),
            ],
            self.event_bus,
            session_store=self.store,
        )
        self.keeper = session_keeper_module.SessionKeeper(
            'main',
            self.router,
            self.store,
            self.event_bus,
        )

    async def turn(self, text: str) -> str:
        """Runs one turn the way the desk runtime does.

        Args:
            text (str): The trigger's text.

        Returns:
            str: The answer.
        """
        trigger = await self.keeper.prepare(_trigger(text))
        result = await self.router.run_turn(trigger)
        return result.text


class TestSessionStore:
    """The session store keeps state, exchanges and summaries on disk."""

    def test_state_survives_a_round_trip(self, tmp_path: Path) -> None:
        """A saved state reads back the same.

        Args:
            tmp_path (Path): A scratch folder.
        """
        store = session_store_module.SessionStore(tmp_path)
        state = session_store_module.SessionState(
            session_id='2026-10-19-1',
            trading_date=_MONDAY,
            routes={
                'claude': session_store_module.RouteState(
                    exchanges_seen=3,
                    runner_state={
                        'session_id': 'abc',
                    },
                ),
            },
        )
        store.save_state(state)
        assert store.load_state() == state

    def test_damaged_state_is_treated_as_missing(self, tmp_path: Path) -> None:
        """A state file that is not JSON does not stop the desk.

        Args:
            tmp_path (Path): A scratch folder.
        """
        (tmp_path / 'state.json').write_text('{not json', encoding='utf-8')
        assert session_store_module.SessionStore(tmp_path).load_state() is None

    def test_session_ids_count_up_within_a_day(self, tmp_path: Path) -> None:
        """Each new session of a day gets the next number.

        Args:
            tmp_path (Path): A scratch folder.
        """
        store = session_store_module.SessionStore(tmp_path)
        assert store.new_session_id(_MONDAY) == '2026-10-19-1'
        assert store.new_session_id(_MONDAY) == '2026-10-19-2'
        assert store.new_session_id(_TUESDAY) == '2026-10-20-1'

    def test_a_line_cut_short_by_a_crash_is_skipped(
        self,
        tmp_path: Path,
    ) -> None:
        """Exchanges before a damaged last line are still read.

        Args:
            tmp_path (Path): A scratch folder.
        """
        store = session_store_module.SessionStore(tmp_path)
        exchange = session_store_module.Exchange(
            trigger_text='hello',
            answer='hi',
            backend_name='claude',
            finished_at='2026-10-19T04:00:00+00:00',
        )
        store.append_exchange('s1', exchange)
        with (tmp_path / 's1.jsonl').open('a', encoding='utf-8') as log:
            log.write('{"trigger_text": "cut')
        assert store.exchanges('s1') == [
            exchange,
        ]

    def test_latest_summary_is_the_newest_day(self, tmp_path: Path) -> None:
        """The newest summary is returned, whatever order the files were written in.

        Args:
            tmp_path (Path): A scratch folder.
        """
        store = session_store_module.SessionStore(tmp_path)
        assert store.latest_summary() is None
        store.write_summary(_TUESDAY, 'Tuesday went well.')
        store.write_summary(_MONDAY, 'Monday was flat.')
        summary = store.latest_summary()
        assert summary.trading_date == _TUESDAY
        assert summary.text == 'Tuesday went well.'


class TestCrashRecovery:
    """After a restart the desk continues the same session."""

    def test_resuming_backend_continues_and_forgetting_one_gets_a_hand_over(
        self,
        tmp_path: Path,
    ) -> None:
        """Claude resumes its own session; Gemma is told what it missed.

        Args:
            tmp_path (Path): A scratch folder.
        """
        calendar = _Calendar(_MONDAY)

        async def before_restart() -> None:
            """Runs two turns on Claude."""
            desk = _Desk(tmp_path, calendar)
            await desk.keeper.start()
            await desk.turn('Buy IDEA?')
            await desk.turn('And now?')

        asyncio.run(before_restart())

        async def after_restart() -> _Desk:
            """Starts a fresh desk on the same folder and runs one turn on each backend.

            Returns:
                _Desk: The restarted desk.
            """
            desk = _Desk(tmp_path, calendar)
            await desk.keeper.start()
            await desk.turn('Still there, Claude?')
            desk.router.prefer('gemma')
            await desk.turn('Still there, Gemma?')
            return desk

        desk = asyncio.run(after_restart())
        assert desk.router.session_id == '2026-10-19-1'
        assert desk.claude.restored_state == {
            'session_id': 'claude-session',
        }
        assert desk.claude.received_texts == [
            'Still there, Claude?',
        ]
        hand_over = desk.gemma.received_texts[0]
        assert 'Trigger: Buy IDEA?' in hand_over
        assert 'Trigger: Still there, Claude?' in hand_over
        assert hand_over.endswith('Still there, Gemma?')
        assert len(desk.router.exchanges) == 4

    def test_start_announces_whether_the_session_was_resumed(
        self,
        tmp_path: Path,
    ) -> None:
        """The first start says "first" and a restart says "resumed".

        Args:
            tmp_path (Path): A scratch folder.
        """
        calendar = _Calendar(_MONDAY)
        reasons = []

        async def start_twice() -> None:
            """Starts two desks on the same folder, one after the other."""
            for _ in range(2):
                desk = _Desk(tmp_path, calendar)
                subscription = desk.event_bus.subscribe()
                await desk.keeper.start()
                published = await subscription.next_event()
                assert published.kind == event_module.EventKind.SESSION_STARTED
                reasons.append(published.payload['reason'])
                await desk.turn('hello')

        asyncio.run(start_twice())
        assert reasons == [
            'first',
            'resumed',
        ]


class TestDailyRollover:
    """A new India day starts a new session, seeded with a summary of the old one."""

    def test_new_day_summarises_and_seeds_the_next_session(
        self,
        tmp_path: Path,
    ) -> None:
        """The model's summary is saved and put in front of the new day's first message.

        Args:
            tmp_path (Path): A scratch folder.
        """
        calendar = _Calendar(_MONDAY)

        async def scenario() -> _Desk:
            """Runs a turn on Monday and two on Tuesday.

            Returns:
                _Desk: The desk.
            """
            desk = _Desk(tmp_path, calendar)
            await desk.keeper.start()
            await desk.turn('Monday trade')
            calendar.today = _TUESDAY
            desk.claude.answer = 'Bought 1 IDEA at 12.21; holding it.'
            await desk.turn('Good morning')
            desk.claude.answer = None
            await desk.turn('Second message')
            return desk

        desk = asyncio.run(scenario())
        summary_request = desk.claude.received_texts[1]
        assert 'session for 2026-10-19 is ending' in summary_request
        assert 'notes/2026-10-19.md' in summary_request
        summary_file = tmp_path / 'summaries' / '2026-10-19.md'
        assert summary_file.read_text(encoding='utf-8') == (
            'Bought 1 IDEA at 12.21; holding it.\n'
        )
        first_of_tuesday = desk.claude.received_texts[2]
        assert 'Summary of your previous session, from 2026-10-19' in (
            first_of_tuesday
        )
        assert 'Bought 1 IDEA at 12.21' in first_of_tuesday
        assert first_of_tuesday.endswith('Good morning')
        assert desk.claude.received_texts[3] == 'Second message'
        assert desk.router.session_id == '2026-10-20-1'

    def test_summary_lists_the_exchanges_when_no_model_answers(
        self,
        tmp_path: Path,
    ) -> None:
        """With every backend down, the summary is the shortened exchanges.

        Args:
            tmp_path (Path): A scratch folder.
        """
        calendar = _Calendar(_MONDAY)

        async def scenario() -> None:
            """Runs a turn on Monday, then rolls over with every backend down."""
            desk = _Desk(tmp_path, calendar)
            await desk.keeper.start()
            await desk.turn('Monday trade')
            calendar.today = _TUESDAY
            desk.claude.available = False
            desk.gemma.available = False
            await desk.keeper.roll_over()

        asyncio.run(scenario())
        text = (tmp_path / 'summaries' / '2026-10-19.md').read_text(
            encoding='utf-8'
        )
        assert text.startswith('No model was available')
        assert '- Trigger: Monday trade' in text
        assert 'Answer from claude: claude answered' in text

    def test_empty_session_is_not_summarised(self, tmp_path: Path) -> None:
        """A day with no turns writes no summary.

        Args:
            tmp_path (Path): A scratch folder.
        """
        calendar = _Calendar(_MONDAY)

        async def scenario() -> _Desk:
            """Starts on Monday and runs the first turn on Tuesday.

            Returns:
                _Desk: The desk.
            """
            desk = _Desk(tmp_path, calendar)
            await desk.keeper.start()
            calendar.today = _TUESDAY
            await desk.turn('Good morning')
            return desk

        desk = asyncio.run(scenario())
        assert not (tmp_path / 'summaries').exists()
        assert desk.claude.received_texts == [
            'Good morning',
        ]


class TestCheckpoints:
    """Checkpoints snapshot the desk's own files and restore them."""

    def test_restore_returns_files_and_leaves_scratch_alone(
        self,
        tmp_path: Path,
    ) -> None:
        """Files created after the checkpoint go; scratch is never touched.

        Args:
            tmp_path (Path): A scratch folder.
        """
        desk_directory = tmp_path / 'desk'
        (desk_directory / 'scratch').mkdir(parents=True)
        (desk_directory / 'Memory.md').write_text('one', encoding='utf-8')
        checkpoints = checkpoints_module.Checkpoints(
            tmp_path / 'main.git',
            desk_directory,
        )
        first = checkpoints.snapshot('first')
        assert checkpoints.snapshot('nothing changed') is None
        (desk_directory / 'Memory.md').write_text('two', encoding='utf-8')
        (desk_directory / 'notes').mkdir()
        (desk_directory / 'notes' / 'a.md').write_text('a', encoding='utf-8')
        (desk_directory / 'scratch' / 'x').write_text('x', encoding='utf-8')
        before = checkpoints.restore(first)
        assert (desk_directory / 'Memory.md').read_text(encoding='utf-8') == (
            'one'
        )
        assert not (desk_directory / 'notes' / 'a.md').exists()
        assert (desk_directory / 'scratch' / 'x').exists()
        checkpoints.restore(before)
        assert (desk_directory / 'notes' / 'a.md').exists()
        assert (desk_directory / 'Memory.md').read_text(encoding='utf-8') == (
            'two'
        )

    def test_unknown_checkpoint_is_refused(self, tmp_path: Path) -> None:
        """Restoring an id that does not exist raises CheckpointError.

        Args:
            tmp_path (Path): A scratch folder.
        """
        desk_directory = tmp_path / 'desk'
        desk_directory.mkdir()
        (desk_directory / 'Memory.md').write_text('one', encoding='utf-8')
        checkpoints = checkpoints_module.Checkpoints(
            tmp_path / 'main.git',
            desk_directory,
        )
        checkpoints.snapshot('first')
        with pytest.raises(checkpoints_module.CheckpointError):
            checkpoints.restore('deadbeef')

    def test_write_file_snapshots_before_writing(self, tmp_path: Path) -> None:
        """write_file takes a checkpoint holding the file as it was.

        Args:
            tmp_path (Path): A scratch folder.
        """
        desk_directory = tmp_path / 'desk'
        desk_directory.mkdir()
        (desk_directory / 'Memory.md').write_text('old', encoding='utf-8')
        checkpoints = checkpoints_module.Checkpoints(
            tmp_path / 'main.git',
            desk_directory,
        )
        tool = write_file_tool.WriteFileTool(
            path_policy.PathPolicy(desk_directory, []),
            checkpoints,
        )
        result = asyncio.run(
            tool.run(
                write_file_tool.WriteFileArguments(
                    path='Memory.md',
                    content='new',
                )
            )
        )
        assert not result.is_error
        listed = checkpoints.list()
        assert listed[0].reason == 'before write_file Memory.md'
        checkpoints.restore(listed[0].checkpoint_id)
        assert (desk_directory / 'Memory.md').read_text(encoding='utf-8') == (
            'old'
        )

    def test_commands_list_and_restore(self, tmp_path: Path) -> None:
        """The command line lists checkpoints and explains how to undo a restore.

        Args:
            tmp_path (Path): A scratch folder.
        """
        desk_directory = tmp_path / 'desk'
        desk_directory.mkdir()
        output = io.StringIO()
        checkpoints = checkpoints_module.Checkpoints(
            tmp_path / 'main.git',
            desk_directory,
        )
        commands = checkpoint_commands.CheckpointCommands(checkpoints, output)
        assert commands.run('list', None) == 0
        assert 'No checkpoints yet.' in output.getvalue()
        (desk_directory / 'Memory.md').write_text('one', encoding='utf-8')
        first = checkpoints.snapshot('first')
        assert commands.run('list', None) == 0
        assert f'{first}  ' in output.getvalue()
        assert commands.run('restore', first) == 0
        assert 'restore that to undo this' in output.getvalue()
        assert commands.run('restore', 'deadbeef') == 1


class TestAddNote:
    """add_note appends dated notes and snapshots first."""

    def test_notes_are_appended_under_a_heading(self, tmp_path: Path) -> None:
        """The first call writes a heading; later calls only add bullets.

        Args:
            tmp_path (Path): A scratch folder.
        """
        desk_directory = tmp_path / 'desk'
        checkpoints = checkpoints_module.Checkpoints(
            tmp_path / 'main.git',
            desk_directory,
        )
        tool = add_note_tool.AddNoteTool(
            desk_directory / 'notes',
            checkpoints,
            lambda: datetime.datetime(2026, 10, 19, 10, 15, tzinfo=_INDIA),
        )
        asyncio.run(
            tool.run(
                add_note_tool.AddNoteArguments(
                    notes=[
                        'IDEA spread widens after 15:00.',
                        'Use limit orders then.',
                    ],
                )
            )
        )
        asyncio.run(
            tool.run(
                add_note_tool.AddNoteArguments(
                    notes=[
                        'Third lesson.',
                    ],
                )
            )
        )
        text = (desk_directory / 'notes' / '2026-10-19.md').read_text(
            encoding='utf-8'
        )
        assert text == (
            '# Notes for 2026-10-19\n'
            '\n'
            '- 10:15 IDEA spread widens after 15:00.\n'
            '- 10:15 Use limit orders then.\n'
            '- 10:15 Third lesson.\n'
        )
        assert checkpoints.list()[0].reason == (
            'before add_note notes/2026-10-19.md'
        )

    def test_more_than_three_notes_are_refused(self) -> None:
        """A call may carry at most three notes, each on one line."""
        with pytest.raises(pydantic.ValidationError):
            add_note_tool.AddNoteArguments(
                notes=[
                    'a',
                    'b',
                    'c',
                    'd',
                ],
            )
        with pytest.raises(pydantic.ValidationError):
            add_note_tool.AddNoteArguments(
                notes=[
                    'two\nlines',
                ],
            )


class TestSessionSearch:
    """search_sessions finds exchanges, summaries, notes and journal actions."""

    def _write_records(self, desk_directory: Path) -> None:
        """Writes one record of each kind.

        Args:
            desk_directory (Path): The desk folder.
        """
        store = session_store_module.SessionStore(desk_directory / 'sessions')
        store.write_summary(_TUESDAY, 'NIFTY recovered the gap by noon.')
        notes = desk_directory / 'notes'
        notes.mkdir()
        (notes / '2026-10-18.md').write_text(
            '# Notes for 2026-10-18\n\n- 10:00 Gap down days reward patience.\n',
            encoding='utf-8',
        )
        journal = desk_directory / 'journal'
        journal.mkdir()
        lines = [
            {
                'kind': 'trigger_received',
                'desk': 'main',
                'payload': {
                    'trigger_id': 't1',
                    'text': 'NIFTY gapped down 1%, what now?',
                },
                'created_at': '2026-10-19T04:00:00+00:00',
            },
            {
                'kind': 'tool_result',
                'desk': 'main',
                'payload': {
                    'trigger_id': 't1',
                    'text': 'NIFTY gap tool output',
                },
                'created_at': '2026-10-19T04:00:01+00:00',
            },
            {
                'kind': 'text',
                'desk': 'main',
                'payload': {
                    'trigger_id': 't1',
                    'text': 'Waited for the first 15 minutes.',
                },
                'created_at': '2026-10-19T04:00:02+00:00',
            },
            {
                'kind': 'tool_call',
                'desk': 'main',
                'payload': {
                    'name': 'search_sessions',
                    'arguments': {
                        'keywords': 'NIFTY gap',
                    },
                },
                'created_at': '2026-10-19T04:30:00+00:00',
            },
            {
                'kind': 'order',
                'desk': 'main',
                'payload': {
                    'action': 'placed',
                    'order': 'buy 1 NIFTY future',
                },
                'created_at': '2026-10-19T05:00:00+00:00',
            },
            {
                'kind': 'model_usage',
                'desk': 'main',
                'payload': {
                    'model': 'NIFTY gap',
                },
                'created_at': '2026-10-19T05:00:00+00:00',
            },
        ]
        (journal / '2026-10-19.jsonl').write_text(
            '\n'.join(json.dumps(line) for line in lines) + '\n',
            encoding='utf-8',
        )

    def test_every_keyword_must_match(self, tmp_path: Path) -> None:
        """Only records holding both keywords are returned, newest first, without tool results or the desk's own searches.

        Args:
            tmp_path (Path): A scratch folder.
        """
        self._write_records(tmp_path)
        result = session_search.SessionSearch(tmp_path).search('nifty gap', 10)
        assert result.matched_every_word
        kinds = [hit.record.kind for hit in result.hits]
        assert kinds == [
            'summary',
            'exchange',
        ]
        exchange = result.hits[1].record.text
        assert exchange == (
            'Trigger: NIFTY gapped down 1%, what now?\n'
            'Answer: Waited for the first 15 minutes.'
        )

    def test_partial_matches_are_shown_when_nothing_matches_fully(
        self,
        tmp_path: Path,
    ) -> None:
        """With no full match, records with some keywords come back.

        Args:
            tmp_path (Path): A scratch folder.
        """
        self._write_records(tmp_path)
        result = session_search.SessionSearch(tmp_path).search(
            'patience banknifty',
            10,
        )
        assert not result.matched_every_word
        assert result.hits[0].record.kind == 'note'

    def test_journal_actions_are_found_but_usage_is_not(
        self,
        tmp_path: Path,
    ) -> None:
        """Orders are searchable; model usage events are left out.

        Args:
            tmp_path (Path): A scratch folder.
        """
        self._write_records(tmp_path)
        tool = search_sessions_tool.SearchSessionsTool(
            session_search.SessionSearch(tmp_path)
        )
        result = asyncio.run(
            tool.run(
                search_sessions_tool.SearchSessionsArguments(
                    keywords='NIFTY future',
                )
            )
        )
        assert '[2026-10-19 · journal]' in result.text
        assert 'buy 1 NIFTY future' in result.text
        assert 'model_usage' not in result.text
