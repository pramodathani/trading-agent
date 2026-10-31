"""Tests for one trader's trigger queue and turn loop."""

import asyncio

import pytest

from trading_agent.configuration import agent_configuration
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trader_runtime
from trading_agent.runtime import trigger as trigger_module
from trading_agent.runtime import turn_runner
from trading_agent.runtime import turn_slots


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


class _GatedTurnRunner(turn_runner.TurnRunner):
    """A turn runner whose turns wait for a gate, and which records releases.

    Attributes:
        gate: Set to let turns finish.
        started: Set once a turn has started.
        releases: How many times release() was called.
    """

    def __init__(self):
        """Creates the runner with the gate shut."""
        self.gate = asyncio.Event()
        self.started = asyncio.Event()
        self.releases = 0

    async def run_turn(
        self,
        trigger: trigger_module.Trigger,
    ) -> turn_runner.TurnResult:
        """Waits for the gate, then replies.

        Args:
            trigger (trigger_module.Trigger): The reason for the turn.

        Returns:
            turn_runner.TurnResult: A reply echoing the trigger's text.
        """
        self.started.set()
        await self.gate.wait()
        return turn_runner.TurnResult(text=f'done: {trigger.text}')

    async def release(self) -> None:
        """Counts the release.

        Returns:
            None.
        """
        self.releases += 1


class TestSleepAndTurnSlots:
    """An idle trader falls asleep and wakes; a turn limit makes extra turns wait."""

    def test_idle_trader_sleeps_and_wakes(self) -> None:
        """After its idle time the trader releases its processes and sleeps; a message wakes it and is answered.

        Returns:
            None.
        """
        runner = _GatedTurnRunner()
        runner.gate.set()

        async def scenario() -> tuple[str, str, list[event_module.Event]]:
            """Lets the trader fall asleep, then wakes it with a message.

            Returns:
                tuple[str, str, list[event_module.Event]]: The state while asleep, the state after the answer, and the events of the woken turn.
            """
            event_bus = event_bus_module.EventBus()
            subscription = event_bus.subscribe()
            trader = trader_runtime.TraderRuntime(
                agent_configuration.TraderConfiguration(name='main'),
                event_bus,
                runner,
                sleep_after_seconds=0.05,
            )
            task = asyncio.create_task(trader.run())
            await asyncio.sleep(0.2)
            asleep = str(trader.state)
            trader.submit(_trigger('wake up'))
            events = await _collect_until_finished(subscription, 1)
            awake = str(trader.state)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            return asleep, awake, events

        asleep, awake, events = asyncio.run(scenario())
        kinds = []
        texts = []
        for published in events:
            kinds.append(published.kind)
            if published.kind == event_module.EventKind.TEXT:
                texts.append(published.payload['text'])

        assert asleep == 'sleeping'
        assert runner.releases == 1
        assert event_module.EventKind.TRADER_SLEEPING in kinds
        assert awake == 'idle'
        assert len(texts) == 1
        assert texts[0].endswith('wake up')

    def test_second_trader_waits_for_the_only_slot(self) -> None:
        """With one slot, a second trader's turn waits until the first finishes.

        Returns:
            None.
        """
        first_runner = _GatedTurnRunner()
        second_runner = _GatedTurnRunner()
        second_runner.gate.set()

        async def scenario() -> tuple[str, bool, bool]:
            """Starts two turns against one slot and opens the first one's gate.

            Returns:
                tuple[str, bool, bool]: The second trader's state while waiting, whether its turn had started before the first finished, and whether it started afterwards.
            """
            event_bus = event_bus_module.EventBus()
            slots = turn_slots.TurnSlots(1)
            first = trader_runtime.TraderRuntime(
                agent_configuration.TraderConfiguration(name='first'),
                event_bus,
                first_runner,
                turn_slots=slots,
            )
            second = trader_runtime.TraderRuntime(
                agent_configuration.TraderConfiguration(name='second'),
                event_bus,
                second_runner,
                turn_slots=slots,
            )
            tasks = [
                asyncio.create_task(first.run()),
                asyncio.create_task(second.run()),
            ]
            first.submit(_trigger('one', 'first'))
            await first_runner.started.wait()
            second.submit(_trigger('two', 'second'))
            await asyncio.sleep(0.05)
            waiting_state = str(second.state)
            started_early = second_runner.started.is_set()
            first_runner.gate.set()
            await asyncio.wait_for(second_runner.started.wait(), 2)
            started_later = second_runner.started.is_set()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            return waiting_state, started_early, started_later

        waiting_state, started_early, started_later = asyncio.run(scenario())

        assert waiting_state == 'waiting'
        assert not started_early
        assert started_later
