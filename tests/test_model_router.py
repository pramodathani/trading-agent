"""Tests for falling back between backends."""

import asyncio

import pytest

from trading_agent.backends import backend
from trading_agent.backends import model_router
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.runtime import turn_runner


class _ScriptedRunner(turn_runner.TurnRunner):
    """A turn runner that fails or answers according to a switch.

    Attributes:
        available: Whether turns succeed.
        received_texts: The trigger texts it was given.
        closed: Whether close was called.
    """

    def __init__(self, name: str, available: bool = True):
        """Creates the runner.

        Args:
            name (str): Used in the answer, to tell runners apart.
            available (bool): Whether turns succeed.
        """
        self._name = name
        self.available = available
        self.received_texts = []
        self.closed = False

    async def run_turn(
        self,
        trigger: trigger_module.Trigger,
    ) -> turn_runner.TurnResult:
        """Answers, or raises when unavailable.

        Args:
            trigger (trigger_module.Trigger): The turn's trigger.

        Returns:
            turn_runner.TurnResult: "<name> answered".

        Raises:
            backend.BackendUnavailableError: When the switch is off.
        """
        self.received_texts.append(trigger.text)
        if not self.available:
            raise backend.BackendUnavailableError(f'{self._name} is down')
        return turn_runner.TurnResult(text=f'{self._name} answered')

    async def close(self) -> None:
        """Records the close."""
        self.closed = True


class _Clock:
    """A clock the test moves forward by hand.

    Attributes:
        now: The current time in seconds.
    """

    def __init__(self):
        """Starts the clock at 1000 seconds."""
        self.now = 1000.0

    def __call__(self) -> float:
        """Reads the clock.

        Returns:
            float: The current time.
        """
        return self.now


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


class _Setup:
    """A router over a primary and a fallback runner.

    Attributes:
        primary: The preferred runner.
        fallback: The second runner.
        clock: The router's clock.
        event_bus: The router's bus.
        router: The router.
    """

    def __init__(self):
        """Builds the router."""
        self.primary = _ScriptedRunner('claude')
        self.fallback = _ScriptedRunner('gemma')
        self.clock = _Clock()
        self.event_bus = event_bus_module.EventBus()
        self.router = model_router.ModelRouter(
            'main',
            [
                model_router.BackendRoute('claude', self.primary),
                model_router.BackendRoute('gemma', self.fallback),
            ],
            self.event_bus,
            clock=self.clock,
        )

    def run(self, text: str) -> str:
        """Runs one turn.

        Args:
            text (str): The trigger's text.

        Returns:
            str: The answer.
        """
        return asyncio.run(self.router.run_turn(_trigger(text))).text


class TestModelRouter:
    """Tests for ModelRouter."""

    def test_preferred_backend_answers_when_available(self) -> None:
        """With every backend up, the first one answers."""
        setup = _Setup()

        assert setup.run('hello') == 'claude answered'
        assert setup.fallback.received_texts == []

    def test_failure_falls_through_to_the_next_backend(self) -> None:
        """When the first backend fails, the second answers in the same turn."""
        setup = _Setup()
        setup.primary.available = False

        assert setup.run('hello') == 'gemma answered'

    def test_failed_backend_waits_before_it_is_tried_again(self) -> None:
        """A failed backend is skipped until its 30 second wait is over."""
        setup = _Setup()
        setup.primary.available = False
        setup.run('first')
        setup.primary.available = True

        setup.clock.now += 10
        assert setup.run('second') == 'gemma answered'
        assert len(setup.primary.received_texts) == 1

        setup.clock.now += 25
        assert setup.run('third') == 'claude answered'

    def test_waiting_periods_grow_and_reset_after_success(self) -> None:
        """Waits go 30, 60, 300, 300 seconds while failing, and back to 30 after a success."""
        route = model_router.BackendRoute('claude', _ScriptedRunner('claude'))
        periods = model_router.DEFAULT_WAITING_PERIODS_SECONDS

        waits = [route.record_failure(0.0, periods) for _ in range(4)]
        route.record_success()
        wait_after_reset = route.record_failure(0.0, periods)

        assert waits == [
            30.0,
            60.0,
            300.0,
            300.0,
        ]
        assert wait_after_reset == 30.0

    def test_returning_backend_is_told_what_it_missed(self) -> None:
        """A backend that comes back gets a hand-over of the turns others answered."""
        setup = _Setup()
        setup.run('What time is it?')
        setup.primary.available = False
        setup.run('Is NIFTY up today?')
        setup.primary.available = True
        setup.clock.now += 31

        setup.run('Anything else?')

        last_text = setup.primary.received_texts[-1]
        assert 'Hand-over' in last_text
        assert 'Is NIFTY up today?' in last_text
        assert 'Answer from gemma: gemma answered' in last_text
        assert 'What time is it?' not in last_text
        assert last_text.endswith('Anything else?')

    def test_every_backend_down_raises_with_each_reason(self) -> None:
        """With no backend available, the error names why each one failed."""
        setup = _Setup()
        setup.primary.available = False
        setup.fallback.available = False

        with pytest.raises(backend.BackendUnavailableError) as raised:
            setup.run('hello')

        assert 'claude is down' in str(raised.value)
        assert 'gemma is down' in str(raised.value)

    def test_events_record_the_failure_and_the_switch(self) -> None:
        """A fallback publishes backend_unavailable for the failure and backend_switch for the change."""
        setup = _Setup()
        setup.primary.available = False

        with setup.event_bus.subscribe() as subscription:
            setup.run('hello')
            kinds = []
            while not subscription._queue.empty():
                kinds.append(subscription._queue.get_nowait().kind)

        assert kinds == [
            event_module.EventKind.BACKEND_UNAVAILABLE,
            event_module.EventKind.BACKEND_SWITCH,
        ]

    def test_close_closes_every_backend(self) -> None:
        """Closing the router closes each backend's runner."""
        setup = _Setup()

        asyncio.run(setup.router.close())

        assert setup.primary.closed
        assert setup.fallback.closed
