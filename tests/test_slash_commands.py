"""Tests for slash commands and the context line, run through a real desk loop."""

import asyncio
import datetime
import json
import zoneinfo
from pathlib import Path

from tests import fakes
from trading_agent.agent import context_usage as context_usage_module
from trading_agent.backends import model_router
from trading_agent.configuration import agent_configuration
from trading_agent.journal import journal_reader
from trading_agent.runtime import desk_runtime
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import slash_commands
from trading_agent.runtime import trigger as trigger_module
from trading_agent.runtime import turn_runner
from trading_agent.skills import skill_library
from trading_agent.subagents import subagent_library
from trading_agent.tools import tool_registry

_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')
_MORNING = datetime.datetime(2026, 10, 19, 10, 0, tzinfo=_INDIA)


class _RecordingRunner(turn_runner.TurnRunner):
    """A turn runner that records what it was asked and whether it was reset.

    Attributes:
        received_texts: The trigger texts it was given.
        reset_count: How many times reset was called.
        snapshot: The context window snapshot it reports, or None.
        thinking_level: The thinking level it reports, changed by set_thinking.
    """

    def __init__(self, name: str):
        """Creates the runner.

        Args:
            name (str): Used in the answer.
        """
        self._name = name
        self.received_texts = []
        self.reset_count = 0
        self.snapshot: context_usage_module.ContextUsage | None = None
        self.thinking_level = 'medium'

    async def run_turn(
        self,
        trigger: trigger_module.Trigger,
    ) -> turn_runner.TurnResult:
        """Records the text and answers.

        Args:
            trigger (trigger_module.Trigger): The turn's trigger.

        Returns:
            turn_runner.TurnResult: "<name> answered".
        """
        self.received_texts.append(trigger.text)
        return turn_runner.TurnResult(text=f'{self._name} answered')

    async def reset(self) -> None:
        """Counts the reset."""
        self.reset_count += 1

    def thinking(self) -> str | None:
        """Reports the thinking level.

        Returns:
            str | None: The level.
        """
        return self.thinking_level

    def set_thinking(self, level: str | None) -> bool:
        """Records the level, with "medium" standing for the configured one.

        Args:
            level (str | None): The level, or None for the configured one.

        Returns:
            bool: Always True.
        """
        self.thinking_level = level or 'medium'
        return True

    def context_usage(self) -> context_usage_module.ContextUsage | None:
        """Reports the snapshot the test set.

        Returns:
            context_usage_module.ContextUsage | None: The snapshot, or None.
        """
        return self.snapshot


class _Desk:
    """A desk with a two-backend router, driven one message at a time.

    Attributes:
        claude: The first backend's runner.
        gemma: The second backend's runner.
        desk: The desk.
    """

    def __init__(
        self,
        tools: tool_registry.ToolRegistry | None = None,
        skills: skill_library.SkillLibrary | None = None,
        parts: slash_commands.CommandParts | None = None,
    ):
        """Builds the desk.

        Args:
            tools (tool_registry.ToolRegistry | None): The desk's tools, or None.
            skills (skill_library.SkillLibrary | None): The desk's skills, or None.
            parts (slash_commands.CommandParts | None): The subagents and journal, or None.
        """
        self.claude = _RecordingRunner('claude')
        self.gemma = _RecordingRunner('gemma')
        self._event_bus = event_bus_module.EventBus()
        router = model_router.ModelRouter(
            'main',
            [
                model_router.BackendRoute('claude', self.claude),
                model_router.BackendRoute('gemma', self.gemma),
            ],
            self._event_bus,
        )
        self.desk = desk_runtime.DeskRuntime(
            agent_configuration.DeskConfiguration(name='main'),
            self._event_bus,
            router,
            'dry_run',
            tools,
            skill_library=skills,
            command_parts=parts,
        )

    def send(self, texts: list[str]) -> list[str]:
        """Sends messages in order and collects each reply.

        Args:
            texts (list[str]): The messages.

        Returns:
            list[str]: The reply to each message.
        """

        async def scenario() -> list[str]:
            """Runs the desk loop until every message is answered.

            Returns:
                list[str]: The replies.
            """
            replies = []
            with self._event_bus.subscribe() as subscription:
                task = asyncio.create_task(self.desk.run())
                for text in texts:
                    self.desk.submit(
                        trigger_module.Trigger.now(
                            trigger_module.TriggerSource.USER_MESSAGE,
                            'main',
                            text,
                        )
                    )
                while len(replies) < len(texts):
                    received = await asyncio.wait_for(
                        subscription.next_event(),
                        timeout=2,
                    )
                    if received.kind == event_module.EventKind.TEXT:
                        replies.append(received.payload['text'])
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            return replies

        return asyncio.run(scenario())


class TestSlashCommands:
    """Tests for the commands and the context line."""

    def test_status_lists_the_models_without_asking_one(self) -> None:
        """/status describes the desk and its backends, and no model is asked."""
        setup = _Desk()

        reply = setup.send(['/status'])[0]

        assert 'Desk: main' in reply
        assert 'Mode: dry_run' in reply
        assert '1. claude: ready' in reply
        assert setup.claude.received_texts == []

    def test_model_command_changes_the_order_and_auto_restores_it(self) -> None:
        """/model gemma puts gemma first; /model auto goes back to the configured order."""
        setup = _Desk()

        replies = setup.send(
            [
                '/model gemma',
                'hello',
                '/model auto',
                'hello again',
            ]
        )

        assert '1. gemma' in replies[0]
        assert replies[1] == 'gemma answered'
        assert '1. claude' in replies[2]
        assert replies[3] == 'claude answered'

    def test_unknown_model_name_is_refused(self) -> None:
        """/model with a name the desk does not have lists the real ones."""
        reply = _Desk().send(['/model gpt'])[0]

        assert "No backend named 'gpt'" in reply

    def test_paused_desk_does_not_ask_any_model(self) -> None:
        """While paused, messages get a fixed reply; after /resume the model answers again."""
        setup = _Desk()

        replies = setup.send(
            [
                '/pause',
                'buy something',
                '/resume',
                'hello',
            ]
        )

        assert 'paused' in replies[1]
        assert replies[3] == 'claude answered'
        assert len(setup.claude.received_texts) == 1

    def test_new_resets_every_backend(self) -> None:
        """/new resets each backend's conversation."""
        setup = _Desk()

        setup.send(['/new'])

        assert setup.claude.reset_count == 1
        assert setup.gemma.reset_count == 1

    def test_bot_name_suffix_is_ignored(self) -> None:
        """A command with the @botname Telegram adds in groups works like the plain command."""
        replies = _Desk().send(
            [
                '/usage@test_bot',
                '/model@test_bot gemma',
            ]
        )

        assert 'Usage is not being tracked on this gateway.' in replies
        assert any('1. gemma' in reply for reply in replies)

    def test_unknown_command_points_to_help(self) -> None:
        """A command the desk does not know points to /help."""
        reply = _Desk().send(['/frobnicate'])[0]

        assert reply == 'Unknown command /frobnicate. Type /help for the list.'

    def test_think_shows_sets_and_restores_each_backends_level(self) -> None:
        """/think lists each backend's level, /think high sets every backend, /think default restores them, and a wrong level is refused."""
        setup = _Desk()

        replies = setup.send(
            [
                '/think',
                '/think high',
                '/think banana',
                '/think default',
            ]
        )

        assert 'claude: medium' in replies[0]
        assert 'gemma: medium' in replies[0]
        assert 'claude: high' in replies[1]
        assert 'from the next turn' in replies[1]
        assert "Unknown thinking level 'banana'" in replies[2]
        assert 'claude: medium' in replies[3]
        assert setup.gemma.thinking_level == 'medium'

    def test_model_sees_the_india_time_and_trigger_source(self) -> None:
        """The message the model receives starts with the context line."""
        setup = _Desk()

        setup.send(['What is the time?'])

        first_line, _, rest = setup.claude.received_texts[0].partition('\n')
        assert first_line.startswith('[India time: ')
        assert first_line.endswith('IST · woken by: user_message]')
        assert rest == 'What is the time?'


def _write_file(path: Path, text: str) -> None:
    """Writes a text file, creating its folder.

    Args:
        path (Path): The file.
        text (str): Its contents.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _journal_line(
    kind: str, payload: dict, created_at: datetime.datetime
) -> str:
    """One journal line, as the trade journal writes it.

    Args:
        kind (str): The event kind.
        payload (dict): The event's details.
        created_at (datetime.datetime): When it happened.

    Returns:
        str: The JSON line.
    """
    return json.dumps(
        {
            'kind': kind,
            'desk': 'main',
            'payload': payload,
            'created_at': created_at.isoformat(),
        }
    )


class TestInformationCommands:
    """Tests for /context, /tools, /skills and /subagents."""

    def test_context_before_any_turn(self) -> None:
        """/context says so when no model has reported its window yet."""
        reply = _Desk().send(['/context'])[0]

        assert 'No turn has run' in reply

    def test_context_shows_the_window_and_its_parts(self) -> None:
        """/context gives the tokens used, the percentage and each part, marking deferred ones."""
        setup = _Desk()
        setup.claude.snapshot = context_usage_module.ContextUsage(
            backend='claude',
            model='opus',
            total_tokens=250000,
            context_window=1000000,
            categories=(
                context_usage_module.ContextCategory('Messages', 200000),
                context_usage_module.ContextCategory('MCP tools', 5000, True),
            ),
            measured=True,
            recorded_at=_MORNING.isoformat(),
        )

        reply = setup.send(['/context'])[0]

        assert (
            'Context window of opus (claude), measured by the model:' in reply
        )
        assert '250,000 of 1,000,000 tokens used (25%)' in reply
        assert '  Messages: 200,000' in reply
        assert '  MCP tools: 5,000 (listed, not loaded)' in reply
        assert 'As of 10:00 IST.' in reply

    def test_tools_lists_each_tool(self) -> None:
        """/tools gives one line per tool; with no tools it says so."""
        registry = tool_registry.ToolRegistry(
            [
                fakes.EchoTool(),
            ],
            5,
        )

        replies = _Desk(tools=registry).send(['/tools'])
        bare = _Desk().send(['/tools'])

        assert '1 tools:' in replies[0]
        assert '- echo: Returns the word in capitals.' in replies[0]
        assert bare == [
            'This desk has no tools.',
        ]

    def test_skills_are_grouped_by_who_wrote_them(self, tmp_path: Path) -> None:
        """/skills separates the user's skills from the ones the desk wrote."""
        _write_file(
            tmp_path / 'installed' / 'opening-range' / 'SKILL.md',
            '---\nname: opening-range\ndescription: Trade the opening range. More detail.\n---\nSteps.\n',
        )
        _write_file(
            tmp_path / 'agent' / 'my-own' / 'SKILL.md',
            '---\nname: my-own\ndescription: A habit the desk learned.\n---\nSteps.\n',
        )
        library = skill_library.SkillLibrary(
            tmp_path / 'installed', tmp_path / 'agent'
        )

        reply = _Desk(skills=library).send(['/skills'])[0]

        assert (
            'Your skills:\n- /opening-range: Trade the opening range.' in reply
        )
        assert (
            "The desk's own skills:\n- /my-own: A habit the desk learned."
            in reply
        )

    def test_subagents_lists_definitions_and_todays_runs(
        self, tmp_path: Path
    ) -> None:
        """/subagents lists each subagent, and today's runs with their outcome, or as running."""
        _write_file(
            tmp_path / 'agents' / 'trade_reviewer.md',
            '---\nname: trade_reviewer\ndescription: Reviews trades. Reads the journal.\n---\nReview.\n',
        )
        started = _MORNING.replace(hour=9, minute=30)
        _write_file(
            tmp_path / 'journal' / '2026-10-19.jsonl',
            '\n'.join(
                [
                    _journal_line(
                        'subagent_started',
                        {
                            'trigger_id': 'one',
                            'subagent': 'trade_reviewer',
                        },
                        started,
                    ),
                    _journal_line(
                        'subagent_finished',
                        {
                            'trigger_id': 'one',
                            'outcome': 'done',
                            'backend': 'claude',
                            'seconds': 42.0,
                        },
                        started,
                    ),
                    _journal_line(
                        'subagent_started',
                        {
                            'trigger_id': 'two',
                            'subagent': 'news_reader',
                        },
                        _MORNING,
                    ),
                ]
            ),
        )
        parts = slash_commands.CommandParts(
            subagent_library=subagent_library.SubagentLibrary(
                tmp_path / 'agents'
            ),
            journal_reader=journal_reader.JournalReader(
                tmp_path / 'journal', lambda: _MORNING
            ),
        )

        reply = _Desk(parts=parts).send(['/subagents'])[0]

        assert 'Subagents:\n- trade_reviewer: Reviews trades.' in reply
        assert '- 09:30 trade_reviewer: done on claude in 42.0 s' in reply
        assert '- 10:00 news_reader: running' in reply

    def test_subagents_with_nothing_to_show(self) -> None:
        """/subagents on a desk without subagents or a journal says so."""
        reply = _Desk().send(['/subagents'])[0]

        assert reply == 'This desk has no subagents and ran none today.'
