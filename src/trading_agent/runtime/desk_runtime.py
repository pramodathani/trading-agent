"""One desk: its queue of triggers and the loop that works through them.

A desk handles one trigger at a time, so it never runs two turns at once. Different desks each have their own runtime and run side by side.

Typical usage example:

  desk = DeskRuntime(desk_configuration, event_bus, turn_runner)
  task = asyncio.create_task(desk.run())
  desk.submit(trigger)
"""

import asyncio
import enum
import logging

from trading_agent.configuration import agent_configuration
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.runtime import turn_runner as turn_runner_module

_LOGGER = logging.getLogger(__name__)


class DeskState(enum.StrEnum):
    """Whether a desk is waiting for a trigger or running a turn."""

    STOPPED = 'stopped'
    IDLE = 'idle'
    BUSY = 'busy'


class DeskRuntime:
    """The running state of one desk.

    Attributes:
        name: The desk's name.
        state: Whether the desk is stopped, idle or running a turn.
    """

    def __init__(
        self,
        desk_configuration: agent_configuration.DeskConfiguration,
        event_bus: event_bus_module.EventBus,
        turn_runner: turn_runner_module.TurnRunner,
    ):
        """Creates the desk without starting its loop.

        Args:
            desk_configuration (agent_configuration.DeskConfiguration): The desk's settings.
            event_bus (event_bus_module.EventBus): The bus to publish the desk's events on.
            turn_runner (turn_runner_module.TurnRunner): What runs each turn.
        """
        self.name = desk_configuration.name
        self.state = DeskState.STOPPED
        self._event_bus = event_bus
        self._turn_runner = turn_runner
        self._trigger_queue = asyncio.Queue()

    def submit(self, trigger: trigger_module.Trigger) -> None:
        """Adds a trigger to the end of the desk's queue.

        Args:
            trigger (trigger_module.Trigger): The trigger to handle.

        Raises:
            ValueError: The trigger is addressed to a different desk.
        """
        if trigger.desk != self.name:
            raise ValueError(
                f'Trigger for desk {trigger.desk!r} was sent to desk {self.name!r}'
            )
        self._trigger_queue.put_nowait(trigger)
        self._publish(
            event_module.EventKind.TRIGGER_RECEIVED,
            trigger.to_json_dictionary(),
        )

    @property
    def queued_count(self) -> int:
        """How many triggers are waiting to be handled."""
        return self._trigger_queue.qsize()

    async def run(self) -> None:
        """Handles triggers one at a time until the task is cancelled."""
        self.state = DeskState.IDLE
        self._publish(event_module.EventKind.DESK_STARTED, {})
        try:
            while True:
                trigger = await self._trigger_queue.get()
                await self._handle(trigger)
        finally:
            await self._turn_runner.close()
            self.state = DeskState.STOPPED
            self._publish(event_module.EventKind.DESK_STOPPED, {})

    async def _handle(self, trigger: trigger_module.Trigger) -> None:
        """Runs one turn for a trigger and publishes what happened.

        A failing turn is recorded as an error event and the desk carries on with the next trigger, because one bad turn must not stop the desk.

        Args:
            trigger (trigger_module.Trigger): The trigger to handle.
        """
        self.state = DeskState.BUSY
        self._publish(
            event_module.EventKind.TURN_STARTED,
            {
                'trigger_id': trigger.trigger_id,
            },
        )
        try:
            result = await self._turn_runner.run_turn(trigger)
        except Exception as error:
            _LOGGER.exception('Turn failed on desk %s', self.name)
            self._publish(
                event_module.EventKind.ERROR,
                {
                    'trigger_id': trigger.trigger_id,
                    'error': repr(error),
                },
            )
        else:
            self._publish(
                event_module.EventKind.TEXT,
                {
                    'trigger_id': trigger.trigger_id,
                    'text': result.text,
                },
            )
        finally:
            self.state = DeskState.IDLE
            self._publish(
                event_module.EventKind.TURN_FINISHED,
                {
                    'trigger_id': trigger.trigger_id,
                },
            )

    def _publish(
        self,
        kind: event_module.EventKind,
        payload: dict,
    ) -> None:
        """Publishes an event from this desk.

        Args:
            kind (event_module.EventKind): What happened.
            payload (dict): The event's details.
        """
        self._event_bus.publish(
            event_module.Event.now(kind, self.name, payload)
        )
