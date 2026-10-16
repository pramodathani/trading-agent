"""One desk: its queue of triggers and the loop that works through them.

A desk handles one trigger at a time, so it never runs two turns at once. Different desks each have their own runtime and run side by side.

A message that starts with a slash is a command and is answered by code. Anything else goes to the desk's turn runner, prefixed with a line stating the India time and what woke the desk; those facts change every turn, so they belong in the message rather than in the system prompt.

Typical usage example:

  desk = DeskRuntime(desk_configuration, event_bus, turn_runner, 'dry_run')
  task = asyncio.create_task(desk.run())
  desk.submit(trigger)
"""

import asyncio
import dataclasses
import enum
import logging
import zoneinfo

from trading_agent.configuration import agent_configuration
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import slash_commands
from trading_agent.runtime import trigger as trigger_module
from trading_agent.runtime import turn_runner as turn_runner_module
from trading_agent.tools import tool_registry as tool_registry_module

_LOGGER = logging.getLogger(__name__)
_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')
_PAUSED_REPLY = 'This desk is paused and did not ask any model. Send /resume to start it again.'


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
        paused: Whether the desk answers without asking any model.
        turn_runner: What runs each turn.
    """

    def __init__(
        self,
        desk_configuration: agent_configuration.DeskConfiguration,
        event_bus: event_bus_module.EventBus,
        turn_runner: turn_runner_module.TurnRunner,
        mode: str = 'dry_run',
        tool_registry: tool_registry_module.ToolRegistry | None = None,
    ):
        """Creates the desk without starting its loop.

        Args:
            desk_configuration (agent_configuration.DeskConfiguration): The desk's settings.
            event_bus (event_bus_module.EventBus): The bus to publish the desk's events on.
            turn_runner (turn_runner_module.TurnRunner): What runs each turn.
            mode (str): "dry_run" or "live", reported by /status.
            tool_registry (tool_registry_module.ToolRegistry | None): The desk's tools, closed when the desk stops, or None.
        """
        self.name = desk_configuration.name
        self.state = DeskState.STOPPED
        self.paused = False
        self.turn_runner = turn_runner
        self._event_bus = event_bus
        self._trigger_queue = asyncio.Queue()
        self._commands = slash_commands.SlashCommands(self, mode)
        self._tool_registry = tool_registry

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
            await self.turn_runner.close()
            if self._tool_registry is not None:
                await self._tool_registry.close()
            self.state = DeskState.STOPPED
            self._publish(event_module.EventKind.DESK_STOPPED, {})

    async def _handle(self, trigger: trigger_module.Trigger) -> None:
        """Answers one trigger and publishes what happened.

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
            text = await self._answer(trigger)
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
                    'text': text,
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

    async def _answer(self, trigger: trigger_module.Trigger) -> str:
        """Answers a trigger with a command, the paused reply, or a model turn.

        Args:
            trigger (trigger_module.Trigger): The trigger.

        Returns:
            str: The answer's text.
        """
        if self._commands.is_command(trigger.text):
            return await self._commands.handle(trigger.text)
        if self.paused:
            return _PAUSED_REPLY
        result = await self.turn_runner.run_turn(self._with_context(trigger))
        return result.text

    def _with_context(
        self,
        trigger: trigger_module.Trigger,
    ) -> trigger_module.Trigger:
        """Puts the India time and the trigger's source in front of its text.

        Args:
            trigger (trigger_module.Trigger): The trigger.

        Returns:
            trigger_module.Trigger: A copy whose text starts with the context line.
        """
        now = trigger.created_at.astimezone(_INDIA)
        context_line = f'[India time: {now:%A %Y-%m-%d %H:%M:%S} IST · woken by: {trigger.source}]'
        return dataclasses.replace(
            trigger, text=f'{context_line}\n{trigger.text}'
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
