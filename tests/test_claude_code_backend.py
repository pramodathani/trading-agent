"""Tests for the Claude Code backend, with a fake client in place of Claude Code."""

import asyncio
from pathlib import Path

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
) -> claude_code_turn_runner.ClaudeCodeTurnRunner:
    """Builds a runner whose settings point at a scratch folder.

    Args:
        event_bus (event_bus_module.EventBus): The bus to publish on.
        oauth_token (str): The subscription token to configure.

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
