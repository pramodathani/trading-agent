"""Tests for falling back from Claude to DeepSeek and back: waiting until a limit resets, and handing over a turn that failed halfway."""

import asyncio
import time
import types

import claude_agent_sdk
import pytest

from tests import fakes
from tests import test_claude_code_backend
from tests import test_deepseek_backend
from tests import test_model_router
from trading_agent.agent import loop_guard
from trading_agent.agent import messages
from trading_agent.backends import backend
from trading_agent.backends import model_router
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.runtime import turn_runner
from trading_agent.tools import tool_call_executor
from trading_agent.tools import tool_registry

_FIVE_HOURS = 5 * 3600.0


class _LimitedRunner(turn_runner.TurnRunner):
    """A runner that refuses with a known reset time while limited, as Claude does at its subscription limit.

    Attributes:
        limited: Whether it refuses.
        received_texts: The trigger texts it was given.
    """

    def __init__(self):
        """Creates the runner, limited."""
        self.limited = True
        self.received_texts = []

    async def run_turn(
        self,
        trigger: trigger_module.Trigger,
    ) -> turn_runner.TurnResult:
        """Answers, or refuses with a reset time.

        Args:
            trigger (trigger_module.Trigger): The turn's trigger.

        Returns:
            turn_runner.TurnResult: "claude answered".

        Raises:
            backend.BackendUnavailableError: While limited, with the time until the limit resets.
        """
        self.received_texts.append(trigger.text)
        if self.limited:
            raise backend.BackendUnavailableError('limit reached', _FIVE_HOURS)
        return turn_runner.TurnResult(text='claude answered')


def _router(
    claude: turn_runner.TurnRunner,
    deepseek: turn_runner.TurnRunner,
    clock: test_model_router._Clock,
    completed_calls=None,
) -> model_router.ModelRouter:
    """Builds a router trying Claude, then DeepSeek.

    Args:
        claude (turn_runner.TurnRunner): The first runner.
        deepseek (turn_runner.TurnRunner): The second runner.
        clock (test_model_router._Clock): The router's clock.
        completed_calls: The record of calls already made, or None.

    Returns:
        model_router.ModelRouter: The router.
    """
    return model_router.ModelRouter(
        'main',
        [
            model_router.BackendRoute('claude', claude),
            model_router.BackendRoute('deepseek', deepseek),
        ],
        event_bus_module.EventBus(),
        clock=clock,
        completed_calls=completed_calls,
    )


class TestFallbackOrder:
    """Tests for the fallback from Claude to DeepSeek."""

    def test_limited_backend_is_skipped_until_its_reset_then_used_again(
        self,
    ) -> None:
        """After Claude refuses with a reset time, it is not tried until then, and is used again afterwards."""
        clock = test_model_router._Clock()
        claude = _LimitedRunner()
        deepseek = test_model_router._ScriptedRunner('deepseek')
        router = _router(claude, deepseek, clock)

        first = asyncio.run(
            router.run_turn(test_model_router._trigger('one'))
        ).text
        clock.now += 3600
        second = asyncio.run(
            router.run_turn(test_model_router._trigger('two'))
        ).text
        claude.limited = False
        clock.now += _FIVE_HOURS
        third = asyncio.run(
            router.run_turn(test_model_router._trigger('three'))
        ).text

        assert first == 'deepseek answered'
        assert second == 'deepseek answered'
        assert len(claude.received_texts) == 2
        assert third == 'claude answered'

    def test_backend_taking_over_is_told_which_calls_already_ran(self) -> None:
        """When the first backend fails partway, the next one gets the calls already made in the turn."""
        clock = test_model_router._Clock()
        claude = _LimitedRunner()
        deepseek = test_model_router._ScriptedRunner('deepseek')
        trigger = test_model_router._trigger('Buy 10 TCS if it dips')
        made = {
            trigger.trigger_id: [
                tool_call_executor.CompletedCall(
                    name='place_order',
                    arguments={
                        'symbol': 'TCS',
                        'quantity': 10,
                    },
                    result_text='Order placed: id 42',
                    is_error=False,
                ),
            ],
        }
        router = _router(
            claude, deepseek, clock, lambda trigger_id: made.get(trigger_id, [])
        )

        asyncio.run(router.run_turn(trigger))

        handed_over = deepseek.received_texts[-1]
        assert claude.received_texts[-1] == 'Buy 10 TCS if it dips'
        assert 'Do not repeat any of them' in handed_over
        assert (
            'place_order {"symbol": "TCS", "quantity": 10} returned: Order placed: id 42'
            in handed_over
        )

    def test_no_note_when_nothing_ran(self) -> None:
        """A backend taking over a turn in which no tool ran gets the trigger unchanged."""
        clock = test_model_router._Clock()
        deepseek = test_model_router._ScriptedRunner('deepseek')
        router = _router(
            _LimitedRunner(), deepseek, clock, lambda trigger_id: []
        )

        asyncio.run(router.run_turn(test_model_router._trigger('Hello')))

        assert deepseek.received_texts[-1] == 'Hello'

    def test_executor_remembers_calls_per_trigger(self) -> None:
        """The executor records each call it runs under its trigger."""
        executor = tool_call_executor.ToolCallExecutor(
            'main',
            tool_registry.ToolRegistry(
                [
                    fakes.EchoTool(),
                ],
                timeout_seconds=1,
            ),
            event_bus_module.EventBus(),
            loop_guard.LoopGuard(maximum_identical_calls=3),
        )
        trigger = test_model_router._trigger('go')

        asyncio.run(
            executor.execute(
                trigger, messages.ToolCall.new('echo', {'word': 'hi'})
            )
        )

        calls = executor.completed_calls(trigger.trigger_id)
        assert [(call.name, call.result_text) for call in calls] == [
            (
                'echo',
                'HI',
            ),
        ]
        assert executor.completed_calls('other') == []

    def test_claude_refusal_says_how_long_until_the_limit_resets(self) -> None:
        """A rejected rate limit makes Claude unavailable until the reset time it reported."""
        runner = test_claude_code_backend._runner(event_bus_module.EventBus())
        resets_at = int(time.time()) + 3600
        info = claude_agent_sdk.RateLimitInfo(
            status='rejected',
            resets_at=resets_at,
            rate_limit_type='five_hour',
        )

        with pytest.raises(backend.BackendUnavailableError) as raised:
            runner._handle_rate_limit(test_model_router._trigger('go'), info)

        assert 3590 <= raised.value.retry_after_seconds <= 3600


class _SwitchableClient:
    """Stands in for a connected ClaudeSDKClient, recording model switches.

    Attributes:
        switched_to: The models set_model was called with.
    """

    def __init__(self):
        """Creates the client."""
        self.switched_to = []

    async def set_model(self, model: str | None = None) -> None:
        """Records a switch.

        Args:
            model (str | None): The new model.
        """
        self.switched_to.append(model)


class TestModelSwitching:
    """Tests for switching a backend to another model of its provider."""

    def test_claude_session_switches_model_before_its_next_turn(self) -> None:
        """A chosen Claude model is applied to the running session once, and returning to the configured model applies it back."""
        runner = test_claude_code_backend._runner(event_bus_module.EventBus())
        client = _SwitchableClient()
        runner._client = client
        runner._applied_model = runner.active_model()

        runner.use_model('claude-haiku-5-5')
        asyncio.run(runner._connected_client(None))
        asyncio.run(runner._connected_client(None))
        runner.use_model(None)
        asyncio.run(runner._connected_client(None))

        assert client.switched_to == [
            'claude-haiku-5-5',
            'opus',
        ]
        assert runner.active_model() == 'opus'

    def test_model_backend_switches_and_returns(self) -> None:
        """An agent-loop backend uses the chosen model name, then its configured one again."""
        model_backend = fakes.ScriptedBackend([])

        model_backend.use_model('other-model')
        chosen = model_backend.model
        model_backend.use_model(None)

        assert chosen == 'other-model'
        assert model_backend.model == 'scripted-model'

    def test_deepseek_cost_is_unknown_for_a_model_without_prices(self) -> None:
        """Switched to a model whose prices are not configured, DeepSeek reports no cost rather than a wrong one."""
        model_backend = test_deepseek_backend._backend()
        usage = types.SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=10,
            prompt_cache_hit_tokens=0,
            prompt_cache_miss_tokens=10,
        )

        model_backend.use_model('deepseek-flash')

        assert model_backend._cost_usd(usage, 0) is None
