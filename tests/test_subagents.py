"""Tests for subagents: definitions, the library, the toolbox, the runner and delegate_task."""

import asyncio
from pathlib import Path

import pydantic
import pytest

from trading_agent.backends import backend
from trading_agent.configuration import agent_configuration
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.runtime import turn_runner
from trading_agent.subagents import subagent_definition
from trading_agent.subagents import subagent_library
from trading_agent.subagents import subagent_prompt_builder
from trading_agent.subagents import subagent_runner
from trading_agent.subagents import subagent_toolbox
from trading_agent.tools import delegate_task_tool
from trading_agent.tools import tool


def _write_agent(
    folder: Path, name: str, extra: str = '', body: str = 'Do it well.'
) -> Path:
    """Writes one subagent file.

    Args:
        folder (Path): The folder.
        name (str): The subagent's name and file name.
        extra (str): More frontmatter lines.
        body (str): Its instructions.

    Returns:
        Path: The file.
    """
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'{name}.md'
    path.write_text(
        f'---\nname: {name}\ndescription: The {name} helper.\n{extra}---\n{body}\n',
        encoding='utf-8',
    )
    return path


class _NamedTool(tool.Tool):
    """A tool with a given name that answers with its name."""

    def __init__(self, name: str):
        """Creates the tool.

        Args:
            name (str): Its name.
        """
        self.name = name
        self.description = f'The {name} tool.'

    async def run(self, arguments: pydantic.BaseModel) -> tool.ToolResult:
        """Answers with the tool's name.

        Args:
            arguments (pydantic.BaseModel): Ignored.

        Returns:
            tool.ToolResult: The name.
        """
        del arguments
        return tool.ToolResult.success(self.name)


class _FakeBashSession:
    """Stands in for a bash session.

    Attributes:
        timeout_seconds: The command time limit the bash tools read.
        closed: Whether close was called.
    """

    def __init__(self):
        """Creates an open session."""
        self.timeout_seconds = 10.0
        self.closed = False

    async def close(self) -> None:
        """Records the close."""
        self.closed = True


class _ScriptedRunner(turn_runner.TurnRunner):
    """A turn runner whose behaviour each test chooses.

    Attributes:
        behaviour: "answer", "slow", "hang", "unavailable" or "crash".
        prompt_text: The system prompt it was built with.
        model: The model name it was built with.
        closed: Whether close was called.
    """

    running_now = 0
    most_at_once = 0

    def __init__(self, behaviour: str, prompt_text: str, model: str):
        """Creates the runner.

        Args:
            behaviour (str): What run_turn does.
            prompt_text (str): The system prompt.
            model (str): The model name.
        """
        self.behaviour = behaviour
        self.prompt_text = prompt_text
        self.model = model
        self.closed = False

    async def run_turn(
        self,
        trigger: trigger_module.Trigger,
    ) -> turn_runner.TurnResult:
        """Acts according to the behaviour.

        Args:
            trigger (trigger_module.Trigger): The task.

        Returns:
            turn_runner.TurnResult: A report naming the model and the task.

        Raises:
            backend.BackendUnavailableError: For "unavailable".
            RuntimeError: For "crash".
        """
        _ScriptedRunner.running_now += 1
        _ScriptedRunner.most_at_once = max(
            _ScriptedRunner.most_at_once,
            _ScriptedRunner.running_now,
        )
        try:
            if self.behaviour == 'slow':
                await asyncio.sleep(0.05)
            if self.behaviour == 'hang':
                await asyncio.sleep(60)
            if self.behaviour == 'unavailable':
                raise backend.BackendUnavailableError('model is down')
            if self.behaviour == 'crash':
                raise RuntimeError('boom')
            return turn_runner.TurnResult(
                text=f'{self.model} reports on: {trigger.text.splitlines()[-1]}'
            )
        finally:
            _ScriptedRunner.running_now -= 1

    async def close(self) -> None:
        """Records the close."""
        self.closed = True


class _Setup:
    """A library, a toolbox and a runner over scripted model runners.

    Attributes:
        agents: The agents folder.
        bash_sessions: The bash sessions the toolbox made.
        runners: The model runners the factory built.
        behaviours: The behaviour for each subagent name.
        runner: The subagent runner.
    """

    def __init__(self, root: Path):
        """Builds the parts.

        Args:
            root (Path): A scratch folder.
        """
        self.agents = root / 'agents'
        self.bash_sessions = []
        self.runners = []
        self.behaviours = {}
        toolbox = subagent_toolbox.SubagentToolbox(
            [
                _NamedTool('get_quote'),
                _NamedTool('web_search'),
                _NamedTool('place_order'),
                _NamedTool('browser_open'),
            ],
            self._bash_session,
            10.0,
        )
        backends = {
            'claude': agent_configuration.BackendConfiguration(
                kind='claude_code',
                model='opus',
                context_window=1000000,
            ),
            'qwen': agent_configuration.BackendConfiguration(
                kind='ollama',
                base_url='http://127.0.0.1:11434',
                model='qwen3.8:27b',
                context_window=32768,
            ),
        }
        self.runner = subagent_runner.SubagentRunner(
            'main',
            'dry_run',
            subagent_library.SubagentLibrary(self.agents),
            toolbox,
            self._make_runner,
            [
                'claude',
                'qwen',
            ],
            backends,
            event_bus_module.EventBus(),
            3,
        )

    def _bash_session(self) -> _FakeBashSession:
        """Makes and records a fake bash session.

        Returns:
            _FakeBashSession: The session.
        """
        session = _FakeBashSession()
        self.bash_sessions.append(session)
        return session

    def _make_runner(
        self,
        backend_name: str,
        backend_configuration: agent_configuration.BackendConfiguration,
        executor: object,
        prompt: subagent_prompt_builder.SubagentPromptBuilder,
        maximum_rounds: int,
    ) -> _ScriptedRunner:
        """Builds a scripted runner, as the desk builder would build a real one.

        Args:
            backend_name (str): The backend.
            backend_configuration (agent_configuration.BackendConfiguration): Its settings.
            executor (object): The task's executor, unused.
            prompt (subagent_prompt_builder.SubagentPromptBuilder): The task's prompt.
            maximum_rounds (int): Unused.

        Returns:
            _ScriptedRunner: The runner.
        """
        del executor, maximum_rounds
        text = prompt.build().text
        name = text.split('"')[1]
        runner = _ScriptedRunner(
            self.behaviours.get(name, 'answer'),
            text,
            f'{backend_name}:{backend_configuration.model}',
        )
        self.runners.append(runner)
        return runner


class TestSubagentDefinition:
    """Subagent files are read in Claude Code's format."""

    def test_fields_are_read_in_both_list_styles(self, tmp_path: Path) -> None:
        """Comma-separated tools, a model list, inherit and the limits.

        Args:
            tmp_path (Path): A scratch folder.
        """
        parser = subagent_definition.SubagentParser()
        first = parser.parse(
            _write_agent(
                tmp_path,
                'news_reader',
                'tools: web_search, web_fetch\nmodel: [qwen, gemma]\nmax_turns: 5\ntimeout: 60\n',
            )
        )
        assert first.tool_names == (
            'web_search',
            'web_fetch',
        )
        assert first.models == (
            'qwen',
            'gemma',
        )
        assert (first.maximum_turns, first.timeout_seconds) == (5, 60)
        assert first.instructions == 'Do it well.'
        second = parser.parse(
            _write_agent(tmp_path, 'reviewer', 'model: inherit\n')
        )
        assert second.models is None
        assert second.tool_names is None
        assert (
            second.timeout_seconds
            == subagent_definition.DEFAULT_TIMEOUT_SECONDS
        )

    def test_bad_limits_and_missing_description_are_refused(
        self,
        tmp_path: Path,
    ) -> None:
        """A timeout above 1,800 seconds and a missing description are errors.

        Args:
            tmp_path (Path): A scratch folder.
        """
        parser = subagent_definition.SubagentParser()
        with pytest.raises(
            subagent_definition.SubagentFormatError, match='timeout'
        ):
            parser.parse(_write_agent(tmp_path, 'slow', 'timeout: 5000\n'))
        bare = tmp_path / 'bare.md'
        bare.write_text('---\nname: bare\n---\nbody\n', encoding='utf-8')
        with pytest.raises(
            subagent_definition.SubagentFormatError, match='description'
        ):
            parser.parse(bare)


class TestSubagentLibrary:
    """The library reads the user's and packages' definitions."""

    def test_user_definition_wins_and_broken_files_are_listed(
        self,
        tmp_path: Path,
    ) -> None:
        """A package's same-named subagent is shadowed; a broken file is reported; the index lists the rest.

        Args:
            tmp_path (Path): A scratch folder.
        """
        _write_agent(tmp_path / 'agents', 'news_reader', body='User version.')
        _write_agent(
            tmp_path / 'package' / 'agents',
            'news_reader',
            body='Package version.',
        )
        _write_agent(tmp_path / 'package' / 'agents', 'tester')
        (tmp_path / 'agents' / 'broken.md').write_text(
            'no frontmatter', encoding='utf-8'
        )
        library = subagent_library.SubagentLibrary(
            tmp_path / 'agents',
            lambda: [
                tmp_path / 'package' / 'agents',
            ],
        )
        assert library.find('news_reader').instructions == 'User version.'
        assert [item.path.name for item in library.broken()] == [
            'broken.md',
        ]
        index = library.index_text()
        assert '- news_reader: The news_reader helper.' in index
        assert '- tester: The tester helper.' in index


class TestSubagentToolbox:
    """Subagents get safe tools by default and never delegate or browse."""

    def test_default_set_and_explicit_list(self, tmp_path: Path) -> None:
        """No list gives the read-only tools the desk has; a list may add orders but never delegate or browser tools.

        Args:
            tmp_path (Path): A scratch folder.
        """
        setup = _Setup(tmp_path)
        toolbox = setup.runner._toolbox
        parser = subagent_definition.SubagentParser()
        default = toolbox.prepare(
            parser.parse(_write_agent(tmp_path / 'a', 'plain'))
        )
        assert default.registry.tool_names == [
            'web_search',
            'get_quote',
        ]
        assert default.bash_session is None
        explicit = toolbox.prepare(
            parser.parse(
                _write_agent(
                    tmp_path / 'a',
                    'trader',
                    'tools: place_order, delegate_task, browser_open, bash_run, bash_check, mystery\n',
                )
            )
        )
        assert explicit.registry.tool_names == [
            'place_order',
            'bash_run',
            'bash_check',
        ]
        assert explicit.refused == [
            'delegate_task',
            'browser_open',
        ]
        assert explicit.unknown == [
            'mystery',
        ]
        assert len(setup.bash_sessions) == 1


class TestSubagentRunner:
    """Tasks run side by side, each with its own limits, and are cleaned up."""

    def test_tasks_run_at_once_and_failures_stay_contained(
        self,
        tmp_path: Path,
    ) -> None:
        """Two slow tasks overlap; a crash and an unknown name do not stop the others.

        Args:
            tmp_path (Path): A scratch folder.
        """
        setup = _Setup(tmp_path)
        _write_agent(setup.agents, 'reader', 'tools: bash_run\n')
        _write_agent(setup.agents, 'reviewer')
        _write_agent(setup.agents, 'crasher')
        setup.behaviours = {
            'reader': 'slow',
            'reviewer': 'slow',
            'crasher': 'crash',
        }
        _ScriptedRunner.most_at_once = 0
        reports = asyncio.run(
            setup.runner.run_all(
                [
                    subagent_runner.SubagentTask('reader', 'INFY news'),
                    subagent_runner.SubagentTask('reviewer', 'Check the trade'),
                    subagent_runner.SubagentTask('crasher', 'Anything'),
                    subagent_runner.SubagentTask('nobody', 'Anything'),
                ]
            )
        )
        assert [report.outcome for report in reports] == [
            'answered',
            'answered',
            'failed',
            'unknown subagent',
        ]
        assert reports[0].text == 'claude:opus reports on: INFY news'
        assert reports[0].backend_name == 'claude'
        assert 'boom' in reports[2].text
        assert 'crasher, reader, reviewer' in reports[3].text
        assert _ScriptedRunner.most_at_once >= 2
        assert all(runner.closed for runner in setup.runners)
        assert setup.bash_sessions[0].closed

    def test_timeout_alias_and_fallback_to_the_desk_order(
        self,
        tmp_path: Path,
    ) -> None:
        """A hanging task times out; sonnet means Claude with sonnet; an unknown model falls back with a note.

        Args:
            tmp_path (Path): A scratch folder.
        """
        setup = _Setup(tmp_path)
        _write_agent(setup.agents, 'hanger', 'timeout: 1\n')
        _write_agent(setup.agents, 'poet', 'model: sonnet\n')
        _write_agent(setup.agents, 'lost', 'model: gpt-9\n')
        setup.behaviours = {
            'hanger': 'hang',
        }
        reports = asyncio.run(
            setup.runner.run_all(
                [
                    subagent_runner.SubagentTask('hanger', 'wait'),
                    subagent_runner.SubagentTask('poet', 'write'),
                    subagent_runner.SubagentTask('lost', 'find'),
                ]
            )
        )
        assert reports[0].outcome == 'timed out'
        assert reports[1].text == 'claude:sonnet reports on: write'
        assert reports[2].notes == ('model gpt-9 matches no backend',)
        assert reports[2].text == 'claude:opus reports on: find'
        poet_prompt = [
            runner.prompt_text
            for runner in setup.runners
            if '"poet"' in runner.prompt_text
        ][0]
        assert poet_prompt.startswith(
            'You are the subagent "poet", working for the "main" desk'
        )
        assert poet_prompt.endswith(
            '===== Your instructions =====\nDo it well.'
        )


class TestDelegateTaskTool:
    """delegate_task joins the reports and labels them."""

    def test_reports_are_joined_and_all_failures_are_an_error(
        self,
        tmp_path: Path,
    ) -> None:
        """A good report is labelled as outside data; when every task fails, the result is an error.

        Args:
            tmp_path (Path): A scratch folder.
        """
        setup = _Setup(tmp_path)
        _write_agent(setup.agents, 'reader')
        _write_agent(setup.agents, 'broken')
        setup.behaviours = {
            'broken': 'unavailable',
        }
        tool_under_test = delegate_task_tool.DelegateTaskTool(setup.runner)
        mixed = asyncio.run(
            tool_under_test.run(
                delegate_task_tool.DelegateTaskArguments(
                    tasks=[
                        delegate_task_tool.DelegatedTask(
                            subagent='reader', task='INFY'
                        ),
                        delegate_task_tool.DelegatedTask(
                            subagent='broken', task='TCS'
                        ),
                    ],
                )
            )
        )
        assert not mixed.is_error
        assert '### reader: answered' in mixed.text
        assert '[Content from the subagent reader' in mixed.text
        assert '### broken: failed' in mixed.text
        failed = asyncio.run(
            tool_under_test.run(
                delegate_task_tool.DelegateTaskArguments(
                    tasks=[
                        delegate_task_tool.DelegatedTask(
                            subagent='broken', task='TCS'
                        ),
                    ],
                )
            )
        )
        assert failed.is_error
        with pytest.raises(pydantic.ValidationError):
            delegate_task_tool.DelegateTaskArguments(
                tasks=[
                    delegate_task_tool.DelegatedTask(
                        subagent='reader', task='x'
                    ),
                ]
                * 5,
            )
