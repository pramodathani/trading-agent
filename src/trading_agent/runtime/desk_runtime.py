"""One desk: its queue of triggers and the loop that works through them.

A desk handles one trigger at a time, so it never runs two turns at once. Different desks each have their own runtime and run side by side.

A message that starts with a slash is a command and is answered by code. Anything else goes to the desk's turn runner, prefixed with a line stating the India time and what woke the desk; those facts change every turn, so they belong in the message rather than in the system prompt. A desk with a session keeper lets it resume the saved session when the desk starts, and roll over to a new session before the first turn of a new day.

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
from trading_agent.journal import usage_tracker as usage_tracker_module
from trading_agent.memory import session_keeper as session_keeper_module
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import slash_commands
from trading_agent.runtime import trigger as trigger_module
from trading_agent.runtime import turn_runner as turn_runner_module
from trading_agent.skills import skill_library as skill_library_module
from trading_agent.tools import tool_registry as tool_registry_module

_LOGGER = logging.getLogger(__name__)
_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')
_NOTHING_TO_DO = 'NOTHING_TO_DO'
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
        usage_tracker: Today's model usage, shown by /usage, or None.
    """

    def __init__(
        self,
        desk_configuration: agent_configuration.DeskConfiguration,
        event_bus: event_bus_module.EventBus,
        turn_runner: turn_runner_module.TurnRunner,
        mode: str = 'dry_run',
        tool_registry: tool_registry_module.ToolRegistry | None = None,
        session_keeper: session_keeper_module.SessionKeeper | None = None,
        skill_library: skill_library_module.SkillLibrary | None = None,
        usage_tracker: usage_tracker_module.UsageTracker | None = None,
    ):
        """Creates the desk without starting its loop.

        Args:
            desk_configuration (agent_configuration.DeskConfiguration): The desk's settings.
            event_bus (event_bus_module.EventBus): The bus to publish the desk's events on.
            turn_runner (turn_runner_module.TurnRunner): What runs each turn.
            mode (str): "dry_run" or "live", reported by /status.
            tool_registry (tool_registry_module.ToolRegistry | None): The desk's tools, closed when the desk stops, or None.
            session_keeper (session_keeper_module.SessionKeeper | None): Keeps the desk's sessions across restarts and days, or None to keep nothing.
            skill_library (skill_library_module.SkillLibrary | None): The desk's skills, invocable as /<skill-name>, or None.
            usage_tracker (usage_tracker_module.UsageTracker | None): Today's model usage, shown by /usage, or None.
        """
        self.name = desk_configuration.name
        self.state = DeskState.STOPPED
        self.paused = False
        self.turn_runner = turn_runner
        self._event_bus = event_bus
        self._trigger_queue = asyncio.Queue()
        self._commands = slash_commands.SlashCommands(
            self,
            mode,
            skill_library,
        )
        self._tool_registry = tool_registry
        self._session_keeper = session_keeper
        self.usage_tracker = usage_tracker

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
            if self._session_keeper is not None:
                await self._session_keeper.start()
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
                    'silent': self._is_silent(trigger, text),
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

    async def roll_over(self) -> str:
        """Ends the desk's session with a summary and starts a fresh one, for /rollover.

        Returns:
            str: What happened, for the reply.
        """
        if self._session_keeper is None:
            return (
                'This desk keeps no sessions, so there is nothing to roll over.'
            )
        session_id = await self._session_keeper.roll_over()
        return f'Rolled over: the day is summarised and session {session_id} has started.'

    def _is_silent(self, trigger: trigger_module.Trigger, text: str) -> bool:
        """Says whether an answer needs no message to the user.

        Args:
            trigger (trigger_module.Trigger): The trigger answered.
            text (str): The answer.

        Returns:
            bool: True for a heartbeat or scheduled job answered with exactly NOTHING_TO_DO.
        """
        scheduled = trigger.source in (
            trigger_module.TriggerSource.HEARTBEAT,
            trigger_module.TriggerSource.CRON,
        )
        return scheduled and text.strip() == _NOTHING_TO_DO

    async def _answer(self, trigger: trigger_module.Trigger) -> str:
        """Answers a trigger with a command, the paused reply, or a model turn.

        Args:
            trigger (trigger_module.Trigger): The trigger.

        Returns:
            str: The answer's text.
        """
        if self._commands.is_command(trigger.text):
            skill_text = self._commands.skill_request(trigger.text)
            if skill_text is None:
                return await self._commands.handle(trigger.text)
            trigger = dataclasses.replace(trigger, text=skill_text)
        if self.paused:
            return _PAUSED_REPLY
        if self._session_keeper is not None:
            trigger = await self._session_keeper.prepare(trigger)
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
