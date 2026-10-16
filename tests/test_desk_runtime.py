"""Tests for one desk's trigger queue and turn loop."""

import asyncio

import pytest

from trading_agent.configuration import agent_configuration
from trading_agent.runtime import desk_runtime
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
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


def _trigger(text: str, desk: str = 'main') -> trigger_module.Trigger:
    """Builds a user-message trigger for the tests.

    Args:
        text (str): The message text.
        desk (str): The desk it is addressed to.

    Returns:
        trigger_module.Trigger: The trigger.
    """
    return trigger_module.Trigger.now(
        trigger_module.TriggerSource.USER_MESSAGE,
        desk,
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


class TestDeskRuntime:
    """Tests for DeskRuntime."""

    def test_triggers_run_one_at_a_time(self) -> None:
        """Three queued triggers never run as overlapping turns."""
        runner = _SlowTurnRunner()

        async def scenario() -> None:
            """Queues three triggers and waits for all three turns."""
            event_bus = event_bus_module.EventBus()
            desk = desk_runtime.DeskRuntime(
                agent_configuration.DeskConfiguration(name='main'),
                event_bus,
                runner,
            )
            with event_bus.subscribe() as subscription:
                task = asyncio.create_task(desk.run())
                for text in [
                    'a',
                    'b',
                    'c',
                ]:
                    desk.submit(_trigger(text))
                await _collect_until_finished(subscription, 3)
                task.cancel()

        asyncio.run(scenario())

        assert runner.most_at_once == 1

    def test_failed_turn_publishes_error_and_desk_continues(self) -> None:
        """A turn that raises becomes an error event, and the next turn still runs."""

        async def scenario() -> list[event_module.EventKind]:
            """Queues two triggers on a runner whose first turn fails.

            Returns:
                list[event_module.EventKind]: The kinds of event published, in order.
            """
            event_bus = event_bus_module.EventBus()
            desk = desk_runtime.DeskRuntime(
                agent_configuration.DeskConfiguration(name='main'),
                event_bus,
                _FailingTurnRunner(),
            )
            with event_bus.subscribe() as subscription:
                task = asyncio.create_task(desk.run())
                desk.submit(_trigger('first'))
                desk.submit(_trigger('second'))
                events = await _collect_until_finished(subscription, 2)
                task.cancel()
            return [received.kind for received in events]

        kinds = asyncio.run(scenario())

        assert event_module.EventKind.ERROR in kinds
        assert kinds.count(event_module.EventKind.TEXT) == 1
        assert kinds[-1] == event_module.EventKind.TURN_FINISHED

    def test_submit_to_wrong_desk_raises(self) -> None:
        """A trigger addressed to another desk is refused."""
        desk = desk_runtime.DeskRuntime(
            agent_configuration.DeskConfiguration(name='main'),
            event_bus_module.EventBus(),
            _SlowTurnRunner(),
        )

        with pytest.raises(ValueError, match='was sent to desk'):
            desk.submit(_trigger('hello', desk='scalper'))
