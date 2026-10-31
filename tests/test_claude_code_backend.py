"""Tests for the Claude Code backend, with a fake client in place of Claude Code."""

import asyncio
import dataclasses
from pathlib import Path
from typing import ClassVar

import claude_agent_sdk
import pytest

from tests import fakes
from trading_agent.agent import loop_guard
from trading_agent.agent import prompt_builder
from trading_agent.backends import backend
from trading_agent.backends import claude_code_turn_runner
from trading_agent.backends import claude_tool_allowlist_hook
from trading_agent.backends import claude_tool_bridge
from trading_agent.configuration import agent_configuration
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.tools import tool_call_executor
from trading_agent.tools import tool_registry


class _FakeClient:
    """Stands in for ClaudeSDKClient, replaying a fixed list of messages.

    Attributes:
        queries: The prompts sent with query().
    """

    def __init__(self, replayed_messages: list):
        """Creates the client.

        Args:
            replayed_messages (list): The messages receive_response() yields.
        """
        self._replayed_messages = replayed_messages
        self.queries = []

    async def query(self, prompt: str) -> None:
        """Records the prompt.

        Args:
            prompt (str): The prompt.
        """
        self.queries.append(prompt)

    async def receive_response(self):
        """Yields the replayed messages.

        Yields:
            object: Each message in order.
        """
        for message in self._replayed_messages:
            yield message

    async def disconnect(self) -> None:
        """Does nothing."""


class _FixedPromptBuilder:
    """Stands in for PromptBuilder with a prompt that never changes."""

    def build(self) -> prompt_builder.SystemPrompt:
        """Returns the fixed prompt.

        Returns:
            prompt_builder.SystemPrompt: The prompt.
        """
        return prompt_builder.SystemPrompt(text='test', fingerprint='fixed')


def _trigger() -> trigger_module.Trigger:
    """Builds a user-message trigger.

    Returns:
        trigger_module.Trigger: The trigger.
    """
    return trigger_module.Trigger.now(
        trigger_module.TriggerSource.USER_MESSAGE,
        'main',
        'What time is it?',
    )


def _executor(event_bus: event_bus_module.EventBus):
    """Builds an executor holding the echo tool.

    Args:
        event_bus (event_bus_module.EventBus): The bus to publish on.

    Returns:
        tool_call_executor.ToolCallExecutor: The executor.
    """
    return tool_call_executor.ToolCallExecutor(
        'main',
        tool_registry.ToolRegistry(
            [
                fakes.EchoTool(),
            ],
            timeout_seconds=1,
        ),
        event_bus,
        loop_guard.LoopGuard(maximum_identical_calls=3),
    )


def _runner(
    event_bus: event_bus_module.EventBus,
    oauth_token: str = 'sk-ant-oat-test',
    sessions_directory: Path = Path('/tmp/trading-agent-test-claude-sessions'),
) -> claude_code_turn_runner.ClaudeCodeTurnRunner:
    """Builds a runner whose settings point at a scratch folder.

    Args:
        event_bus (event_bus_module.EventBus): The bus to publish on.
        oauth_token (str): The subscription token to configure.
        sessions_directory (Path): Where the runner looks for Claude Code's session files.

    Returns:
        claude_code_turn_runner.ClaudeCodeTurnRunner: The runner, never connected.
    """
    return claude_code_turn_runner.ClaudeCodeTurnRunner(
        'main',
        'claude',
        agent_configuration.BackendConfiguration(
            kind='claude_code',
            model='opus',
            context_window=1000000,
        ),
        claude_tool_bridge.ClaudeToolBridge(_executor(event_bus)),
        event_bus,
        claude_code_turn_runner.ClaudeCodeSettings(
            prompt_builder=_FixedPromptBuilder(),
            oauth_token=oauth_token,
            working_directory=Path('/tmp/trading-agent-test-scratch'),
            maximum_rounds=5,
            sessions_directory=sessions_directory,
            compression_threshold=0.70,
            emergency_compression_threshold=0.85,
        ),
    )


def _rate_limit(status: str) -> claude_agent_sdk.RateLimitEvent:
    """Builds a rate-limit message.

    Args:
        status (str): "allowed", "allowed_warning" or "rejected".

    Returns:
        claude_agent_sdk.RateLimitEvent: The message.
    """
    return claude_agent_sdk.RateLimitEvent(
        rate_limit_info=claude_agent_sdk.RateLimitInfo(
            status=status,
            rate_limit_type='five_hour',
            resets_at=1792000000,
        ),
        uuid='u1',
        session_id='s1',
    )


def _drain(subscription: event_bus_module.EventSubscription) -> list:
    """Takes every event waiting in a subscription.

    Args:
        subscription (event_bus_module.EventSubscription): The subscription.

    Returns:
        list: The waiting events, oldest first.
    """
    events = []
    while True:
        try:
            events.append(subscription._queue.get_nowait())
        except asyncio.QueueEmpty:
            return events


class TestClaudeToolAllowlistHook:
    """Tests for the PreToolUse allow list."""

    def test_own_tool_is_allowed(self) -> None:
        """A trading-agent tool passes with an empty decision."""
        hook = claude_tool_allowlist_hook.ClaudeToolAllowlistHook(
            [
                'mcp__trading_agent__get_time',
            ]
        )

        decision = asyncio.run(
            hook(
                {
                    'tool_name': 'mcp__trading_agent__get_time',
                },
                None,
                None,
            )
        )

        assert decision == {}

    def test_built_in_bash_is_denied(self) -> None:
        """Claude Code's own Bash is refused, because it would bypass the sandbox."""
        hook = claude_tool_allowlist_hook.ClaudeToolAllowlistHook(
            [
                'mcp__trading_agent__get_time',
            ]
        )

        decision = asyncio.run(
            hook(
                {
                    'tool_name': 'Bash',
                },
                None,
                None,
            )
        )

        assert decision['hookSpecificOutput']['permissionDecision'] == 'deny'


class TestClaudeToolBridge:
    """Tests for handing tools to Claude Code."""

    def test_handler_runs_through_the_executor(self) -> None:
        """A Claude tool call runs the registry tool and publishes call and result events."""
        event_bus = event_bus_module.EventBus()
        bridge = claude_tool_bridge.ClaudeToolBridge(_executor(event_bus))
        bridge.current_trigger = _trigger()
        handler = claude_tool_bridge.ClaudeToolHandler(bridge, 'echo')

        with event_bus.subscribe() as subscription:
            answer = asyncio.run(
                handler(
                    {
                        'word': 'infy',
                    }
                )
            )
            kinds = [published.kind for published in _drain(subscription)]

        assert answer['content'][0]['text'] == 'INFY'
        assert answer['is_error'] is False
        assert kinds == [
            event_module.EventKind.TOOL_CALL,
            event_module.EventKind.TOOL_RESULT,
        ]

    def test_claude_tool_names_use_the_mcp_prefix(self) -> None:
        """Tools are offered to Claude under the trading_agent server's prefix."""
        bridge = claude_tool_bridge.ClaudeToolBridge(
            _executor(event_bus_module.EventBus())
        )

        assert bridge.claude_tool_names() == [
            'mcp__trading_agent__echo',
        ]


class TestClaudeCodeTurnRunner:
    """Tests for the Claude Code turn runner."""

    def test_api_key_in_environment_makes_claude_unavailable(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """With ANTHROPIC_API_KEY set the runner refuses, rather than bill the API.

        Args:
            monkeypatch (pytest.MonkeyPatch): Sets the environment variable for this test only.
        """
        monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-ant-api-test')
        runner = _runner(event_bus_module.EventBus())

        with pytest.raises(
            backend.BackendUnavailableError, match='bill the API'
        ):
            asyncio.run(runner.run_turn(_trigger()))

    def test_missing_token_makes_claude_unavailable(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Without the subscription token the runner refuses to start Claude Code.

        Args:
            monkeypatch (pytest.MonkeyPatch): Removes ANTHROPIC_API_KEY for this test only.
        """
        monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
        runner = _runner(event_bus_module.EventBus(), oauth_token='')

        with pytest.raises(backend.BackendUnavailableError, match='not set'):
            asyncio.run(runner.run_turn(_trigger()))

    def test_response_is_streamed_and_recorded(self) -> None:
        """Text pieces, the limit status and usage are published, and the result is the answer."""
        event_bus = event_bus_module.EventBus()
        runner = _runner(event_bus)
        client = _FakeClient(
            [
                _rate_limit('allowed'),
                claude_agent_sdk.StreamEvent(
                    uuid='u2',
                    session_id='s1',
                    event={
                        'type': 'content_block_delta',
                        'delta': {
                            'type': 'text_delta',
                            'text': 'It is 10:15.',
                        },
                    },
                ),
                claude_agent_sdk.AssistantMessage(
                    content=[
                        claude_agent_sdk.TextBlock(text='It is 10:15.'),
                    ],
                    model='claude-opus-5-5',
                ),
                claude_agent_sdk.ResultMessage(
                    subtype='success',
                    duration_ms=1000,
                    duration_api_ms=900,
                    is_error=False,
                    num_turns=2,
                    session_id='session-42',
                    total_cost_usd=0.01,
                    usage={
                        'input_tokens': 30,
                        'output_tokens': 12,
                    },
                    result='It is 10:15.',
                ),
            ]
        )

        with event_bus.subscribe() as subscription:
            result = asyncio.run(runner._read_response(client, _trigger()))
            kinds = [published.kind for published in _drain(subscription)]

        assert result.text == 'It is 10:15.'
        assert runner.session_id == 'session-42'
        assert kinds == [
            event_module.EventKind.RATE_LIMIT,
            event_module.EventKind.TEXT_DELTA,
            event_module.EventKind.MODEL_USAGE,
        ]

    def test_rejected_rate_limit_makes_claude_unavailable(self) -> None:
        """When the subscription limit is reached, Claude is reported unavailable."""
        runner = _runner(event_bus_module.EventBus())
        client = _FakeClient(
            [
                _rate_limit('rejected'),
            ]
        )

        with pytest.raises(
            backend.BackendUnavailableError, match='limit is reached'
        ):
            asyncio.run(runner._read_response(client, _trigger()))

    def test_error_result_makes_claude_unavailable(self) -> None:
        """A turn that Claude Code reports as failed is reported unavailable."""
        runner = _runner(event_bus_module.EventBus())
        client = _FakeClient(
            [
                claude_agent_sdk.ResultMessage(
                    subtype='error_during_execution',
                    duration_ms=10,
                    duration_api_ms=0,
                    is_error=True,
                    num_turns=0,
                    session_id='s1',
                ),
            ]
        )

        with pytest.raises(
            backend.BackendUnavailableError, match='turn failed'
        ):
            asyncio.run(runner._read_response(client, _trigger()))


class _ChangingPromptBuilder:
    """Stands in for PromptBuilder, with a prompt the test can change.

    Attributes:
        text: The current prompt text.
    """

    def __init__(self):
        """Starts with version one."""
        self.text = 'rules version one'

    def build(self) -> prompt_builder.SystemPrompt:
        """Returns the current prompt.

        Returns:
            prompt_builder.SystemPrompt: The prompt, fingerprinted by its text.
        """
        return prompt_builder.SystemPrompt(
            text=self.text, fingerprint=self.text
        )


class TestClaudePromptUpdates:
    """Tests for delivering changed instructions into a running session."""

    def test_changed_files_are_sent_once_inside_the_message(self) -> None:
        """Unchanged files send the trigger alone; changed files are delivered once, then not again."""
        runner = _runner(event_bus_module.EventBus())
        builder = _ChangingPromptBuilder()
        runner._settings = dataclasses.replace(
            runner._settings,
            prompt_builder=builder,
        )
        runner._session_prompt_fingerprint = builder.build().fingerprint
        trigger = _trigger()

        unchanged = runner._query_text(builder.build(), trigger)
        builder.text = 'rules version two'
        changed = runner._query_text(builder.build(), trigger)
        runner._session_prompt_fingerprint = builder.build().fingerprint
        after_delivery = runner._query_text(builder.build(), trigger)

        assert unchanged == trigger.text
        assert changed.startswith(
            '[The complete current versions of your instruction files'
        )
        assert 'rules version two' in changed
        assert changed.endswith(trigger.text)
        assert after_delivery == trigger.text


class TestClaudeEnvironment:
    """Tests for the environment Claude Code is started with."""

    def test_tradingmachine_settings_are_blanked(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Every TRADINGMACHINE_ variable reaches Claude Code empty, and the token and compaction window are set.

        Args:
            monkeypatch (pytest.MonkeyPatch): Sets the variable for this test only.
        """
        monkeypatch.setenv('TRADINGMACHINE_MONGODB_PASSWORD', 'very-secret')
        runner = _runner(event_bus_module.EventBus())

        environment = runner._environment()

        assert environment['TRADINGMACHINE_MONGODB_PASSWORD'] == ''
        assert environment['CLAUDE_CODE_OAUTH_TOKEN'] == 'sk-ant-oat-test'
        assert environment['CLAUDE_CODE_AUTO_COMPACT_WINDOW'] == '850000'


class TestClaudeSessionRestore:
    """Tests for resuming Claude's session after a restart."""

    def test_saved_session_is_resumed_when_claude_code_still_has_it(
        self,
        tmp_path: Path,
    ) -> None:
        """A session whose file exists is resumed, and saved again unchanged.

        Args:
            tmp_path (Path): Stands in for ~/.claude/projects.
        """
        project_folder = tmp_path / '-home-pramod-trader-scratch'
        project_folder.mkdir()
        (project_folder / 'abc-123.jsonl').write_text('{}', encoding='utf-8')
        runner = _runner(
            event_bus_module.EventBus(),
            sessions_directory=tmp_path,
        )
        state = {
            'session_id': 'abc-123',
            'prompt_fingerprint': 'f1',
        }

        resumed = asyncio.run(runner.restore_state(state))

        assert resumed
        assert runner.session_id == 'abc-123'
        assert runner.saved_state() == state

    def test_missing_session_file_starts_afresh(self, tmp_path: Path) -> None:
        """A session Claude Code no longer has is not resumed.

        Args:
            tmp_path (Path): Stands in for ~/.claude/projects.
        """
        runner = _runner(
            event_bus_module.EventBus(),
            sessions_directory=tmp_path,
        )

        resumed = asyncio.run(
            runner.restore_state(
                {
                    'session_id': 'gone',
                }
            )
        )

        assert not resumed
        assert runner.session_id is None
        assert runner.saved_state() is None


class _ConnectingClient:
    """Stands in for ClaudeSDKClient when the runner connects, recording each client made.

    Attributes:
        made: Every client created, oldest first.
        options: The options this client was created with.
        disconnected: Whether disconnect was called.
    """

    made: ClassVar[list] = []

    def __init__(self, options: claude_agent_sdk.ClaudeAgentOptions):
        """Records the client and its options.

        Args:
            options (claude_agent_sdk.ClaudeAgentOptions): The session's options.
        """
        self.options = options
        self.disconnected = False
        _ConnectingClient.made.append(self)

    async def connect(self) -> None:
        """Does nothing."""

    async def disconnect(self) -> None:
        """Records the disconnection."""
        self.disconnected = True


class TestClaudeThinking:
    """Tests for /think on the Claude runner."""

    def test_levels_set_effort_or_switch_thinking_off(self) -> None:
        """A level becomes the effort, off disables thinking, and None goes back to the configured effort."""
        runner = _runner(event_bus_module.EventBus())

        assert runner.thinking() == 'default'
        runner.set_thinking('high')
        high = runner._options('prompt')
        runner.set_thinking('off')
        off = runner._options('prompt')
        runner.set_thinking(None)

        assert high.effort == 'high'
        assert high.thinking is None
        assert off.thinking == {
            'type': 'disabled',
        }
        assert runner.thinking() == 'default'
        assert runner._options('prompt').effort is None

    def test_changed_level_restarts_claude_code_at_the_next_turn(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Claude Code is restarted with the new effort only when the level changed, and keeps the client otherwise.

        Args:
            monkeypatch (pytest.MonkeyPatch): Replaces ClaudeSDKClient for this test only.
        """
        monkeypatch.setattr(
            claude_code_turn_runner.claude_agent_sdk,
            'ClaudeSDKClient',
            _ConnectingClient,
        )
        _ConnectingClient.made = []
        runner = _runner(event_bus_module.EventBus())
        prompt = _FixedPromptBuilder().build()

        first = asyncio.run(runner._connected_client(prompt))
        again = asyncio.run(runner._connected_client(prompt))
        runner.set_thinking('low')
        after_change = asyncio.run(runner._connected_client(prompt))

        assert again is first
        assert after_change is not first
        assert first.disconnected
        assert after_change.options.effort == 'low'
        assert len(_ConnectingClient.made) == 2


class TestClaudeSideQuestion:
    """Tests for side questions on the Claude runner."""

    def test_side_question_forks_the_session_and_deletes_the_fork(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The question runs in a fork of the trader's session with every tool refused, and the fork's file is deleted while the trader's is kept.

        Args:
            monkeypatch (pytest.MonkeyPatch): Replaces the SDK's query and removes ANTHROPIC_API_KEY for this test only.
            tmp_path (Path): Stands in for Claude Code's sessions folder.
        """
        monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
        project = tmp_path / 'project'
        project.mkdir()
        (project / 'session-42.jsonl').write_text('{}', encoding='utf-8')
        (project / 'fork-1.jsonl').write_text('{}', encoding='utf-8')
        seen_options = []

        async def fake_query(prompt, options):
            """Records the options and replays an answer from a fork.

            Args:
                prompt (str): The question sent.
                options (claude_agent_sdk.ClaudeAgentOptions): The fork's options.

            Yields:
                object: An assistant message, then the result.
            """
            seen_options.append((prompt, options))
            yield claude_agent_sdk.AssistantMessage(
                content=[
                    claude_agent_sdk.TextBlock(
                        text='Because the trend turned.'
                    ),
                ],
                model='claude-opus-5-5',
            )
            yield claude_agent_sdk.ResultMessage(
                subtype='success',
                duration_ms=100,
                duration_api_ms=90,
                is_error=False,
                num_turns=1,
                session_id='fork-1',
                result='Because the trend turned.',
            )

        monkeypatch.setattr(
            claude_code_turn_runner.claude_agent_sdk, 'query', fake_query
        )
        runner = _runner(
            event_bus_module.EventBus(), sessions_directory=tmp_path
        )
        runner.session_id = 'session-42'

        answer = asyncio.run(runner.side_question('Why?'))

        prompt, options = seen_options[0]
        assert answer == 'Because the trend turned.'
        assert prompt.endswith('\nWhy?')
        assert options.resume == 'session-42'
        assert options.fork_session
        assert options.allowed_tools == []
        assert runner.session_id == 'session-42'
        assert not (project / 'fork-1.jsonl').exists()
        assert (project / 'session-42.jsonl').exists()
