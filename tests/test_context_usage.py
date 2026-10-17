"""Tests for the context-window snapshots, from each kind of runner to the gateway route."""

import asyncio
from typing import Any

import claude_agent_sdk
import fastapi
import fastapi.testclient

from tests import fakes
from tests import test_claude_code_backend
from trading_agent.agent import agent_loop
from trading_agent.agent import agent_turn_runner
from trading_agent.agent import context_usage
from trading_agent.agent import conversation as conversation_module
from trading_agent.agent import loop_guard
from trading_agent.agent import messages
from trading_agent.agent import prompt_builder
from trading_agent.backends import backend
from trading_agent.backends import model_router
from trading_agent.gateway import access_guard
from trading_agent.gateway.routes import desk_routes
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.runtime import turn_runner
from trading_agent.tools import tool_call_executor
from trading_agent.tools import tool_registry

_TOKEN = 'test-access-token'
_CLAUDE_REPORT = {
    'categories': [
        {
            'name': 'Messages',
            'tokens': 46400,
            'color': 'messageColor',
        },
        {
            'name': 'MCP tools',
            'tokens': 60800,
            'color': 'inactive',
            'isDeferred': True,
        },
        {
            'name': 'Free space',
            'tokens': 853900,
            'color': 'inactive',
        },
    ],
    'totalTokens': 113200,
    'maxTokens': 967000,
    'rawMaxTokens': 1000000,
    'percentage': 11.3,
    'model': 'claude-opus-5-5',
}


def _trigger(text: str = 'Hello') -> trigger_module.Trigger:
    """Builds a user-message trigger.

    Args:
        text (str): The message.

    Returns:
        trigger_module.Trigger: The trigger.
    """
    return trigger_module.Trigger.now(
        trigger_module.TriggerSource.USER_MESSAGE,
        'main',
        text,
    )


def _snapshot(backend_name: str) -> context_usage.ContextUsage:
    """Builds a small snapshot named after a backend.

    Args:
        backend_name (str): The backend's name.

    Returns:
        context_usage.ContextUsage: The snapshot.
    """
    return context_usage.ContextUsage(
        backend=backend_name,
        model='model',
        total_tokens=10,
        context_window=100,
        categories=(
            context_usage.ContextCategory('Messages', 10),
        ),
        measured=True,
        recorded_at='2026-10-18T00:00:00+00:00',
    )


class _SnapshotRunner(turn_runner.TurnRunner):
    """A turn runner that answers or fails, and reports a fixed snapshot."""

    def __init__(self, name: str, available: bool):
        """Creates the runner.

        Args:
            name (str): The backend name its snapshot carries.
            available (bool): Whether turns succeed.
        """
        self._name = name
        self._available = available

    async def run_turn(
        self,
        trigger: trigger_module.Trigger,
    ) -> turn_runner.TurnResult:
        """Answers, or raises when unavailable.

        Args:
            trigger (trigger_module.Trigger): The turn's trigger.

        Returns:
            turn_runner.TurnResult: A fixed answer.

        Raises:
            backend.BackendUnavailableError: When the runner is unavailable.
        """
        del trigger
        if not self._available:
            raise backend.BackendUnavailableError(f'{self._name} is down')
        return turn_runner.TurnResult(text='answered')

    def context_usage(self) -> context_usage.ContextUsage | None:
        """Reports the fixed snapshot.

        Returns:
            context_usage.ContextUsage | None: A snapshot named after the runner.
        """
        return _snapshot(self._name)


class _FixedPromptBuilder:
    """Stands in for PromptBuilder with a 300-character prompt."""

    def build(self) -> prompt_builder.SystemPrompt:
        """Returns the fixed prompt.

        Returns:
            prompt_builder.SystemPrompt: The prompt.
        """
        return prompt_builder.SystemPrompt(text='x' * 300, fingerprint='fixed')


class _ReportingClient:
    """Stands in for ClaudeSDKClient's get_context_usage.

    Attributes:
        failing: Whether the call raises instead of answering.
    """

    def __init__(self, failing: bool = False):
        """Creates the client.

        Args:
            failing (bool): Whether the call raises instead of answering.
        """
        self.failing = failing

    async def get_context_usage(self) -> dict[str, Any]:
        """Answers with the fixed report.

        Returns:
            dict[str, Any]: The report.

        Raises:
            claude_agent_sdk.ClaudeSDKError: When the client is set to fail.
        """
        if self.failing:
            raise claude_agent_sdk.ClaudeSDKError('not connected')
        return _CLAUDE_REPORT


class _StandInDesk:
    """Stands in for a desk runtime, holding only its turn runner.

    Attributes:
        turn_runner: The desk's runner.
    """

    def __init__(self, runner: turn_runner.TurnRunner):
        """Creates the desk.

        Args:
            runner (turn_runner.TurnRunner): The desk's runner.
        """
        self.turn_runner = runner


class _StandInParts:
    """Stands in for a desk's parts, holding only its tools.

    Attributes:
        tools: The desk's tool registry.
    """

    def __init__(self):
        """Creates the parts with the echo tool."""
        self.tools = tool_registry.ToolRegistry(
            [
                fakes.EchoTool(),
            ],
            timeout_seconds=1,
        )


def _agent_runner(context_window: int) -> agent_turn_runner.AgentTurnRunner:
    """Builds an agent runner on a scripted model that answers in one round.

    Args:
        context_window (int): The window to give the runner.

    Returns:
        agent_turn_runner.AgentTurnRunner: The runner.
    """
    event_bus = event_bus_module.EventBus()
    executor = tool_call_executor.ToolCallExecutor(
        'main',
        _StandInParts().tools,
        event_bus,
        loop_guard.LoopGuard(maximum_identical_calls=2),
    )
    loop = agent_loop.AgentLoop(
        'main',
        fakes.ScriptedBackend(
            [
                fakes.text_reply('Hello there.'),
            ]
        ),
        executor,
        event_bus,
        maximum_rounds=3,
    )
    return agent_turn_runner.AgentTurnRunner(
        loop,
        _FixedPromptBuilder(),
        context_window,
    )


class TestContextUsage:
    """Tests for ContextUsage."""

    def test_claude_report_keeps_its_categories(self) -> None:
        """Claude's categories, total and raw window are kept, and deferred ones are marked."""
        usage = context_usage.ContextUsage.from_claude('claude', _CLAUDE_REPORT)

        assert usage.measured
        assert usage.total_tokens == 113200
        assert usage.context_window == 1000000
        assert usage.model == 'claude-opus-5-5'
        assert [category.name for category in usage.categories] == [
            'Messages',
            'MCP tools',
            'Free space',
        ]
        assert usage.categories[1].deferred
        assert not usage.categories[0].deferred

    def test_estimate_before_any_call_adds_up(self) -> None:
        """Before the model reports a count, the parts are estimated and the free space is the rest."""
        conversation = conversation_module.Conversation('p' * 300)
        conversation.append(messages.ConversationMessage.user('m' * 60))

        usage = context_usage.ContextUsage.estimate(
            'qwen',
            'qwen3.8:27b',
            1000,
            conversation,
            [],
        )

        tokens = {category.name: category.tokens for category in usage.categories}
        assert not usage.measured
        assert tokens[context_usage.SYSTEM_PROMPT] == 100
        assert tokens[context_usage.MESSAGES] == 20
        assert usage.total_tokens == 100 + tokens[context_usage.TOOLS] + 20
        assert tokens[context_usage.FREE_SPACE] == 1000 - usage.total_tokens

    def test_estimate_after_a_call_is_scaled_to_the_measured_total(self) -> None:
        """Once the model reports a count, the rough parts are scaled to add up to it, keeping their proportions."""
        conversation = conversation_module.Conversation('p' * 300)
        conversation.append(messages.ConversationMessage.user('m' * 300))
        conversation.record_usage(500)
        definitions = [
            {
                'name': 'x' * 2000,
            },
        ]

        usage = context_usage.ContextUsage.estimate(
            'qwen',
            'qwen3.8:27b',
            1000,
            conversation,
            definitions,
        )

        tokens = {category.name: category.tokens for category in usage.categories}
        assert usage.total_tokens == 500
        assert tokens[context_usage.SYSTEM_PROMPT] + tokens[context_usage.TOOLS] + tokens[context_usage.MESSAGES] == 500
        assert abs(tokens[context_usage.SYSTEM_PROMPT] - tokens[context_usage.MESSAGES]) <= 1
        assert tokens[context_usage.TOOLS] > tokens[context_usage.SYSTEM_PROMPT]
        assert tokens[context_usage.FREE_SPACE] == 500

    def test_payload_is_plain_values(self) -> None:
        """The payload lists each category as a dictionary."""
        payload = _snapshot('claude').to_payload()

        assert payload['backend'] == 'claude'
        assert payload['categories'] == [
            {
                'name': 'Messages',
                'tokens': 10,
                'deferred': False,
            },
        ]


class TestRunnerSnapshots:
    """Tests for the runners' context_usage methods."""

    def test_agent_runner_without_a_window_has_no_snapshot(self) -> None:
        """A runner that does not know its window reports nothing."""
        assert _agent_runner(0).context_usage() is None

    def test_agent_runner_estimates_after_a_turn(self) -> None:
        """After a turn, the agent runner's snapshot names the backend and counts the tools."""
        runner = _agent_runner(32768)
        asyncio.run(runner.run_turn(_trigger()))

        usage = runner.context_usage()

        assert usage is not None
        assert usage.backend == 'scripted'
        assert usage.context_window == 32768
        tokens = {category.name: category.tokens for category in usage.categories}
        assert tokens[context_usage.TOOLS] > 0

    def test_claude_runner_records_the_report(self) -> None:
        """Claude's report is kept until the session is reset."""
        runner = test_claude_code_backend._runner(event_bus_module.EventBus())

        assert runner.context_usage() is None
        asyncio.run(runner._record_context_usage(_ReportingClient()))
        usage = runner.context_usage()

        assert usage is not None
        assert usage.total_tokens == 113200
        asyncio.run(runner.reset())
        assert runner.context_usage() is None

    def test_claude_runner_keeps_the_old_report_when_the_call_fails(self) -> None:
        """A failed call leaves the previous snapshot in place."""
        runner = test_claude_code_backend._runner(event_bus_module.EventBus())
        asyncio.run(runner._record_context_usage(_ReportingClient()))

        asyncio.run(runner._record_context_usage(_ReportingClient(failing=True)))

        assert runner.context_usage() is not None

    def test_router_reports_the_backend_that_answered_last(self) -> None:
        """Before any turn the first backend's snapshot is given, and afterwards the one that answered."""
        router = model_router.ModelRouter(
            'main',
            [
                model_router.BackendRoute('claude', _SnapshotRunner('claude', available=False)),
                model_router.BackendRoute('qwen', _SnapshotRunner('qwen', available=True)),
            ],
            event_bus_module.EventBus(),
        )

        before = router.context_usage()
        asyncio.run(router.run_turn(_trigger()))
        after = router.context_usage()

        assert before is not None
        assert before.backend == 'claude'
        assert after is not None
        assert after.backend == 'qwen'


class TestContextRoute:
    """Tests for GET /api/desks/{desk}/context."""

    def _client(self, runner: turn_runner.TurnRunner) -> fastapi.testclient.TestClient:
        """Builds a client for the desk routes with one desk.

        Args:
            runner (turn_runner.TurnRunner): The desk's runner.

        Returns:
            fastapi.testclient.TestClient: The client, sending the access token.
        """
        application = fastapi.FastAPI()
        application.include_router(
            desk_routes.DeskRoutes(
                {
                    'main': _StandInDesk(runner),
                },
                access_guard.AccessGuard(_TOKEN),
                {
                    'main': _StandInParts(),
                },
            ).router()
        )
        return fastapi.testclient.TestClient(
            application,
            headers={
                'Authorization': f'Bearer {_TOKEN}',
            },
        )

    def test_snapshot_and_tools_are_returned(self) -> None:
        """The route gives the runner's snapshot and the desk's tool names."""
        client = self._client(_SnapshotRunner('claude', available=True))

        answer = client.get('/api/desks/main/context')

        assert answer.status_code == 200
        body = answer.json()
        assert body['usage']['backend'] == 'claude'
        assert body['tools'] == [
            'echo',
        ]

    def test_runner_without_a_snapshot_gives_none(self) -> None:
        """A runner with no snapshot gives null usage."""
        client = self._client(turn_runner.TurnRunner())

        body = client.get('/api/desks/main/context').json()

        assert body['usage'] is None

    def test_unknown_desk_is_not_found(self) -> None:
        """An unknown desk answers 404."""
        client = self._client(turn_runner.TurnRunner())

        assert client.get('/api/desks/nobody/context').status_code == 404
