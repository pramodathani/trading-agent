"""Tests for one trader's trigger queue and turn loop."""

import asyncio

import pytest

from trading_agent.configuration import agent_configuration
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trader_runtime
from trading_agent.runtime import trigger as trigger_module
from trading_agent.runtime import turn_runner


class _SlowTurnRunner(turn_runner.TurnRunner):
    """A turn runner that records how many turns run at once."""

    def __init__(self):
        """Creates the runner with no turns running."""
        self.running_now = 0
        self.most_at_once = 0

    async def run_turn(
        self,
        trigger: trigger_module.Trigger,
    ) -> turn_runner.TurnResult:
        """Waits briefly while counting concurrent turns.

        Args:
            trigger (trigger_module.Trigger): The reason for the turn.

        Returns:
            turn_runner.TurnResult: A reply echoing the trigger's text.
        """
        self.running_now += 1
        self.most_at_once = max(self.most_at_once, self.running_now)
        await asyncio.sleep(0.01)
        self.running_now -= 1
        return turn_runner.TurnResult(text=f'done: {trigger.text}')


class _FailingTurnRunner(turn_runner.TurnRunner):
    """A turn runner that fails on the first turn only."""

    def __init__(self):
        """Creates the runner before any turn."""
        self.turn_count = 0

    async def run_turn(
        self,
        trigger: trigger_module.Trigger,
    ) -> turn_runner.TurnResult:
        """Raises on the first call and replies normally afterwards.

        Args:
            trigger (trigger_module.Trigger): The reason for the turn.

        Returns:
            turn_runner.TurnResult: A reply echoing the trigger's text.

        Raises:
            RuntimeError: On the first call.
        """
        self.turn_count += 1
        if self.turn_count == 1:
            raise RuntimeError('model exploded')
        return turn_runner.TurnResult(text=f'done: {trigger.text}')


def _trigger(text: str, trader: str = 'main') -> trigger_module.Trigger:
    """Builds a user-message trigger for the tests.

    Args:
        text (str): The message text.
        trader (str): The trader it is addressed to.

    Returns:
        trigger_module.Trigger: The trigger.
    """
    return trigger_module.Trigger.now(
        trigger_module.TriggerSource.USER_MESSAGE,
        trader,
        text,
    )


async def _collect_until_finished(
    subscription: event_bus_module.EventSubscription,
    finished_turns: int,
) -> list[event_module.Event]:
    """Reads events until a number of turns have finished.

    Args:
        subscription (event_bus_module.EventSubscription): The subscription to read from.
        finished_turns (int): How many turn_finished events to wait for.

    Returns:
        list[event_module.Event]: Every event read, in order.
    """
    events = []
    seen_finished = 0
    while seen_finished < finished_turns:
        received = await asyncio.wait_for(subscription.next_event(), timeout=2)
        events.append(received)
        if received.kind == event_module.EventKind.TURN_FINISHED:
            seen_finished += 1
    return events


class TestTraderRuntime:
    """Tests for TraderRuntime."""

    def test_triggers_run_one_at_a_time(self) -> None:
        """Three queued triggers never run as overlapping turns."""
        runner = _SlowTurnRunner()

        async def scenario() -> None:
            """Queues three triggers and waits for all three turns."""
            event_bus = event_bus_module.EventBus()
            trader = trader_runtime.TraderRuntime(
                agent_configuration.TraderConfiguration(name='main'),
                event_bus,
                runner,
            )
            with event_bus.subscribe() as subscription:
                task = asyncio.create_task(trader.run())
                for text in [
                    'a',
                    'b',
                    'c',
                ]:
                    trader.submit(_trigger(text))
                await _collect_until_finished(subscription, 3)
                task.cancel()

        asyncio.run(scenario())

        assert runner.most_at_once == 1

    def test_failed_turn_publishes_error_and_trader_continues(self) -> None:
        """A turn that raises becomes an error event, and the next turn still runs."""

        async def scenario() -> list[event_module.EventKind]:
            """Queues two triggers on a runner whose first turn fails.

            Returns:
                list[event_module.EventKind]: The kinds of event published, in order.
            """
            event_bus = event_bus_module.EventBus()
            trader = trader_runtime.TraderRuntime(
                agent_configuration.TraderConfiguration(name='main'),
                event_bus,
                _FailingTurnRunner(),
            )
            with event_bus.subscribe() as subscription:
                task = asyncio.create_task(trader.run())
                trader.submit(_trigger('first'))
                trader.submit(_trigger('second'))
                events = await _collect_until_finished(subscription, 2)
                task.cancel()
            return [received.kind for received in events]

        kinds = asyncio.run(scenario())

        assert event_module.EventKind.ERROR in kinds
        assert kinds.count(event_module.EventKind.TEXT) == 1
        assert kinds[-1] == event_module.EventKind.TURN_FINISHED

    def test_submit_to_wrong_trader_raises(self) -> None:
        """A trigger addressed to another trader is refused."""
        trader = trader_runtime.TraderRuntime(
            agent_configuration.TraderConfiguration(name='main'),
            event_bus_module.EventBus(),
            _SlowTurnRunner(),
        )

        with pytest.raises(ValueError, match='was sent to trader'):
            trader.submit(_trigger('hello', trader='scalper'))


class _ClosingTurnRunner(turn_runner.TurnRunner):
    """A turn runner that records whether it was closed."""

    def __init__(self):
        """Creates the runner, not yet closed."""
        self.closed = False

    async def close(self) -> None:
        """Records the close."""
        self.closed = True


class TestTraderRuntimeShutdown:
    """Tests for stopping a trader."""

    def test_stopping_the_trader_closes_its_turn_runner(self) -> None:
        """Cancelling the trader loop calls the runner's close, so Claude Code is stopped."""
        runner = _ClosingTurnRunner()

        async def scenario() -> None:
            """Starts the trader loop and cancels it."""
            trader = trader_runtime.TraderRuntime(
                agent_configuration.TraderConfiguration(name='main'),
                event_bus_module.EventBus(),
                runner,
            )
            task = asyncio.create_task(trader.run())
            await asyncio.sleep(0.01)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        asyncio.run(scenario())

        assert runner.closed
