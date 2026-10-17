"""One desk: its queue of triggers and the loop that works through them.

A desk handles one trigger at a time, so it never runs two turns at once. Different desks each have their own runtime and run side by side.

A message from the user that arrives while a model turn is running is steering: it goes to the desk's steering inbox and the running turn picks it up at its next tool round, instead of waiting for the turn to end. `/stop` skips the queue altogether and cancels the running turn. Commands that only read the desk, such as `/status`, also skip the queue and are answered beside the running turn.

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
from trading_agent.runtime import steering_inbox as steering_inbox_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.runtime import turn_runner as turn_runner_module
from trading_agent.scheduling import market_status as market_status_module
from trading_agent.skills import skill_library as skill_library_module
from trading_agent.tools import tool_registry as tool_registry_module

_LOGGER = logging.getLogger(__name__)
_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')
_NOTHING_TO_DO = 'NOTHING_TO_DO'
_PAUSED_REPLY = 'This desk is paused and did not ask any model. Send /resume to start it again.'
_STOP_COMMAND = '/stop'
_STOPPED_REPLY = 'Stopped by the user before the turn finished. Tools that had already run are not undone.'


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
        market_status: market_status_module.MarketStatus | None = None,
        steering_inbox: steering_inbox_module.SteeringInbox | None = None,
        command_parts: slash_commands.CommandParts | None = None,
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
            market_status (market_status_module.MarketStatus | None): Describes the market for the context line, or None to leave it out.
            steering_inbox (steering_inbox_module.SteeringInbox | None): Where mid-turn messages wait for the running turn, shared with the turn runner; None creates one that only this desk reads.
            command_parts (slash_commands.CommandParts | None): The subagents and journal some commands read, or None; the desk's own tool registry is added to it.
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
            dataclasses.replace(
                command_parts or slash_commands.CommandParts(),
                tool_registry=tool_registry,
            ),
        )
        self._tool_registry = tool_registry
        self._session_keeper = session_keeper
        self.usage_tracker = usage_tracker
        self._market_status = market_status
        self.steering_inbox = (
            steering_inbox
            or steering_inbox_module.SteeringInbox(event_bus, self.name)
        )
        self._running_trigger_id: str | None = None
        self._turn_task: asyncio.Task | None = None
        self._stop_requested = False
        self._beside_tasks: set[asyncio.Task] = set()

    def submit(self, trigger: trigger_module.Trigger) -> None:
        """Adds a trigger to the end of the desk's queue.

        Args:
            trigger (trigger_module.Trigger): The trigger to handle.

        A /stop is answered at once instead of being queued, a read-only command such as /status is answered beside the running turn, and a user message that arrives during a model turn goes to the steering inbox.

        Raises:
            ValueError: The trigger is addressed to a different desk.
        """
        if trigger.desk != self.name:
            raise ValueError(
                f'Trigger for desk {trigger.desk!r} was sent to desk {self.name!r}'
            )
        if self._commands.command_name(trigger.text) == _STOP_COMMAND:
            self._publish(
                event_module.EventKind.TRIGGER_RECEIVED,
                trigger.to_json_dictionary(),
            )
            self._stop(trigger)
            return
        if self._answers_beside(trigger):
            self._publish(
                event_module.EventKind.TRIGGER_RECEIVED,
                trigger.to_json_dictionary(),
            )
            self._start_beside(trigger)
            return
        if self._can_steer(trigger):
            self.steering_inbox.add(trigger, self._running_trigger_id)
            payload = trigger.to_json_dictionary()
            payload['steering_into'] = self._running_trigger_id
            self._publish(event_module.EventKind.TRIGGER_RECEIVED, payload)
            return
        self._trigger_queue.put_nowait(trigger)
        self._publish(
            event_module.EventKind.TRIGGER_RECEIVED,
            trigger.to_json_dictionary(),
        )

    def _can_steer(self, trigger: trigger_module.Trigger) -> bool:
        """Says whether a trigger should steer the running turn rather than wait.

        Args:
            trigger (trigger_module.Trigger): The new trigger.

        Returns:
            bool: True for a user message without attachments, not a command, while a model turn runs. A message with pictures or documents becomes its own turn, because pictures cannot be handed to a turn already running.
        """
        return (
            trigger.source == trigger_module.TriggerSource.USER_MESSAGE
            and self._running_trigger_id is not None
            and not trigger.attachments
            and not self._commands.is_command(trigger.text)
        )

    def _answers_beside(self, trigger: trigger_module.Trigger) -> bool:
        """Says whether a trigger is a command answered beside the running turn instead of queued.

        Args:
            trigger (trigger_module.Trigger): The new trigger.

        Returns:
            bool: True for a read-only command without attachments, sent while an event loop runs to answer it.
        """
        if trigger.attachments or not self._commands.is_instant(trigger.text):
            return False
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return False
        return True

    def _start_beside(self, trigger: trigger_module.Trigger) -> None:
        """Starts answering a command in its own task, keeping the task until it ends.

        Args:
            trigger (trigger_module.Trigger): The command.
        """
        task = asyncio.get_running_loop().create_task(
            self._answer_beside(trigger)
        )
        self._beside_tasks.add(task)
        task.add_done_callback(self._beside_tasks.discard)

    async def _answer_beside(self, trigger: trigger_module.Trigger) -> None:
        """Answers a command beside the running turn and publishes the answer as a turn of its own.

        Args:
            trigger (trigger_module.Trigger): The command.
        """
        self._publish(
            event_module.EventKind.TURN_STARTED,
            {
                'trigger_id': trigger.trigger_id,
            },
        )
        try:
            text = await self._commands.handle(trigger.text)
        except Exception as error:
            _LOGGER.exception('Command failed on desk %s', self.name)
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
                    'silent': False,
                },
            )
        finally:
            self._publish(
                event_module.EventKind.TURN_FINISHED,
                {
                    'trigger_id': trigger.trigger_id,
                },
            )

    def _stop(self, trigger: trigger_module.Trigger) -> None:
        """Cancels the running model turn, and answers the /stop at once.

        Args:
            trigger (trigger_module.Trigger): The /stop trigger.
        """
        if self._turn_task is not None and not self._turn_task.done():
            self._stop_requested = True
            self._turn_task.cancel()
            text = 'Stopping the running turn.'
        else:
            text = 'Nothing is running, so there is nothing to stop.'
        self._publish(
            event_module.EventKind.TURN_STARTED,
            {
                'trigger_id': trigger.trigger_id,
            },
        )
        self._publish(
            event_module.EventKind.TEXT,
            {
                'trigger_id': trigger.trigger_id,
                'text': text,
                'silent': False,
            },
        )
        self._publish(
            event_module.EventKind.TURN_FINISHED,
            {
                'trigger_id': trigger.trigger_id,
            },
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
            for task in list(self._beside_tasks):
                task.cancel()
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
        self._running_trigger_id = trigger.trigger_id
        self._turn_task = asyncio.create_task(
            self.turn_runner.run_turn(self._with_context(trigger))
        )
        try:
            result = await self._turn_task
        except asyncio.CancelledError:
            if not self._stop_requested:
                raise
            self._stop_requested = False
            self._publish(
                event_module.EventKind.STOPPED,
                {
                    'trigger_id': trigger.trigger_id,
                },
            )
            return _STOPPED_REPLY
        finally:
            self._running_trigger_id = None
            self._turn_task = None
            self._queue_undelivered()
        return result.text

    def _queue_undelivered(self) -> None:
        """Queues the mid-turn messages the turn never picked up as their own turns."""
        for trigger in self.steering_inbox.take_undelivered():
            self._trigger_queue.put_nowait(trigger)

    def _with_context(
        self,
        trigger: trigger_module.Trigger,
    ) -> trigger_module.Trigger:
        """Puts the India time and the trigger's source in front of its text, and a note for each attachment after it.

        Args:
            trigger (trigger_module.Trigger): The trigger.

        Returns:
            trigger_module.Trigger: A copy whose text starts with the context line and ends with the attachment notes.
        """
        now = trigger.created_at.astimezone(_INDIA)
        market = ''
        if self._market_status is not None:
            market = f' · market: {self._market_status.describe(now)}'
        context_line = f'[India time: {now:%A %Y-%m-%d %H:%M:%S} IST · woken by: {trigger.source}{market}]'
        lines = [
            context_line,
            trigger.text,
        ]
        for attachment in trigger.attachments:
            lines.append(attachment.describe_for_model())
        return dataclasses.replace(trigger, text='\n'.join(lines))

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
