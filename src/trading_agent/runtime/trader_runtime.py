"""One trader: its queue of triggers and the loop that works through them.

A trader handles one trigger at a time, so it never runs two turns at once. Different traders each have their own runtime and run side by side.

A message from the user that arrives while a model turn is running is steering: it goes to the trader's steering inbox and the running turn picks it up at its next tool round, instead of waiting for the turn to end. `/stop` skips the queue altogether and cancels the running turn. Commands that only read the trader, such as `/status`, also skip the queue and are answered beside the running turn, and so is `/btw`, which asks a model a side question.

A message that starts with a slash is a command and is answered by code. Anything else goes to the trader's turn runner, prefixed with a line stating the India time and what woke the trader; those facts change every turn, so they belong in the message rather than in the system prompt. A trader with a session keeper lets it resume the saved session when the trader starts, and roll over to a new session before the first turn of a new day.

Typical usage example:

  trader = TraderRuntime(trader_configuration, event_bus, turn_runner, 'dry_run')
  task = asyncio.create_task(trader.run())
  trader.submit(trigger)
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
from trading_agent.runtime import turn_slots as turn_slots_module
from trading_agent.scheduling import market_status as market_status_module
from trading_agent.skills import skill_library as skill_library_module
from trading_agent.tools import tool_registry as tool_registry_module

_LOGGER = logging.getLogger(__name__)
_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')
_NOTHING_TO_DO = 'NOTHING_TO_DO'
_PAUSED_REPLY = 'This trader is paused and did not ask any model. Send /resume to start it again.'
_STOP_COMMAND = '/stop'
_STOPPED_REPLY = 'Stopped by the user before the turn finished. Tools that had already run are not undone.'


class TraderState(enum.StrEnum):
    """Whether a trader is waiting for a trigger, asleep, waiting for a turn slot, or running a turn."""

    STOPPED = 'stopped'
    IDLE = 'idle'
    SLEEPING = 'sleeping'
    WAITING = 'waiting'
    BUSY = 'busy'


class TraderRuntime:
    """The running state of one trader.

    Attributes:
        name: The trader's name.
        state: Whether the trader is stopped, idle or running a turn.
        paused: Whether the trader answers without asking any model.
        turn_runner: What runs each turn.
        usage_tracker: Today's model usage, shown by /usage, or None.
    """

    def __init__(
        self,
        trader_configuration: agent_configuration.TraderConfiguration,
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
        sleep_after_seconds: float | None = None,
        turn_slots: turn_slots_module.TurnSlots | None = None,
    ):
        """Creates the trader without starting its loop.

        Args:
            trader_configuration (agent_configuration.TraderConfiguration): The trader's settings.
            event_bus (event_bus_module.EventBus): The bus to publish the trader's events on.
            turn_runner (turn_runner_module.TurnRunner): What runs each turn.
            mode (str): "dry_run" or "live", reported by /status.
            tool_registry (tool_registry_module.ToolRegistry | None): The trader's tools, closed when the trader stops, or None.
            session_keeper (session_keeper_module.SessionKeeper | None): Keeps the trader's sessions across restarts and days, or None to keep nothing.
            skill_library (skill_library_module.SkillLibrary | None): The trader's skills, invocable as /<skill-name>, or None.
            usage_tracker (usage_tracker_module.UsageTracker | None): Today's model usage, shown by /usage, or None.
            market_status (market_status_module.MarketStatus | None): Describes the market for the context line, or None to leave it out.
            steering_inbox (steering_inbox_module.SteeringInbox | None): Where mid-turn messages wait for the running turn, shared with the turn runner; None creates one that only this trader reads.
            command_parts (slash_commands.CommandParts | None): The subagents and journal some commands read, or None; the trader's own tool registry is added to it.
            sleep_after_seconds (float | None): How long the trader may sit idle before it stops its model processes, or None to keep them running.
            turn_slots (turn_slots_module.TurnSlots | None): The limit on model turns running at once, shared by every trader, or None for no limit.
        """
        self.name = trader_configuration.name
        self.state = TraderState.STOPPED
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
        self._loop: asyncio.AbstractEventLoop | None = None
        self._sleep_after_seconds = sleep_after_seconds
        self._turn_slots = turn_slots or turn_slots_module.TurnSlots(None)

    def submit(self, trigger: trigger_module.Trigger) -> None:
        """Adds a trigger to the end of the trader's queue.

        Args:
            trigger (trigger_module.Trigger): The trigger to handle.

        A /stop is answered at once instead of being queued, a read-only command such as /status is answered beside the running turn, and a user message that arrives during a model turn goes to the steering inbox.

        Raises:
            ValueError: The trigger is addressed to a different trader.
        """
        if trigger.trader != self.name:
            raise ValueError(
                f'Trigger for trader {trigger.trader!r} was sent to trader {self.name!r}'
            )
        if self._called_from_another_thread():
            self._loop.call_soon_threadsafe(self._accept, trigger)
            return
        self._accept(trigger)

    def command_catalogue(self) -> list[dict[str, str]]:
        """The trader's commands and usable skills, for a client's command menu.

        Returns:
            list[dict[str, str]]: The entries, as SlashCommands.catalogue describes them.
        """
        return self._commands.catalogue()

    def _called_from_another_thread(self) -> bool:
        """Says whether submit was called outside the trader's event loop, such as from a web route running in a worker thread.

        Returns:
            bool: True when the trader's loop is running and the caller is not on it.
        """
        if self._loop is None or not self._loop.is_running():
            return False
        try:
            return asyncio.get_running_loop() is not self._loop
        except RuntimeError:
            return True

    def _accept(self, trigger: trigger_module.Trigger) -> None:
        """Answers, steers or queues a trigger, on the trader's event loop when it runs.

        Args:
            trigger (trigger_module.Trigger): The trigger, already checked to be for this trader.
        """
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
            bool: True for a read-only command, or one that runs in the background such as /btw, without attachments, sent while an event loop runs to answer it.
        """
        if trigger.attachments:
            return False
        if not self._commands.is_instant(
            trigger.text
        ) and not self._commands.is_background(trigger.text):
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
            _LOGGER.exception('Command failed on trader %s', self.name)
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
        self.state = TraderState.IDLE
        self._loop = asyncio.get_running_loop()
        self._publish(event_module.EventKind.TRADER_STARTED, {})
        try:
            if self._session_keeper is not None:
                await self._session_keeper.start()
            while True:
                trigger = await self._next_trigger()
                await self._handle(trigger)
        finally:
            for task in list(self._beside_tasks):
                task.cancel()
            await self.turn_runner.close()
            if self._tool_registry is not None:
                await self._tool_registry.close()
            self.state = TraderState.STOPPED
            self._publish(event_module.EventKind.TRADER_STOPPED, {})

    async def _next_trigger(self) -> trigger_module.Trigger:
        """Waits for the next trigger, falling asleep when none comes for a while.

        Returns:
            trigger_module.Trigger: The trigger.
        """
        if (
            self._sleep_after_seconds is None
            or self.state == TraderState.SLEEPING
        ):
            return await self._trigger_queue.get()
        try:
            return await asyncio.wait_for(
                self._trigger_queue.get(), self._sleep_after_seconds
            )
        except TimeoutError:
            await self._fall_asleep()
        return await self._trigger_queue.get()

    async def _fall_asleep(self) -> None:
        """Stops the model processes kept between turns; the next trigger wakes the trader and resumes its session.

        Returns:
            None.
        """
        await self.turn_runner.release()
        self.state = TraderState.SLEEPING
        self._publish(event_module.EventKind.TRADER_SLEEPING, {})

    async def _handle(self, trigger: trigger_module.Trigger) -> None:
        """Answers one trigger and publishes what happened.

        A failing turn is recorded as an error event and the trader carries on with the next trigger, because one bad turn must not stop the trader.

        Args:
            trigger (trigger_module.Trigger): The trigger to handle.
        """
        self.state = TraderState.BUSY
        self._publish(
            event_module.EventKind.TURN_STARTED,
            {
                'trigger_id': trigger.trigger_id,
            },
        )
        try:
            text = await self._answer(trigger)
        except Exception as error:
            _LOGGER.exception('Turn failed on trader %s', self.name)
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
            self.state = TraderState.IDLE
            self._publish(
                event_module.EventKind.TURN_FINISHED,
                {
                    'trigger_id': trigger.trigger_id,
                },
            )

    async def roll_over(self) -> str:
        """Ends the trader's session with a summary and starts a fresh one, for /rollover.

        Returns:
            str: What happened, for the reply.
        """
        if self._session_keeper is None:
            return 'This trader keeps no sessions, so there is nothing to roll over.'
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
        if not self._turn_slots.is_free():
            self.state = TraderState.WAITING
        async with self._turn_slots.slot():
            self.state = TraderState.BUSY
            return await self._run_model_turn(trigger)

    async def _run_model_turn(self, trigger: trigger_module.Trigger) -> str:
        """Runs one model turn, or answers the /stop that cancelled it.

        Args:
            trigger (trigger_module.Trigger): The trigger, prepared by the session keeper.

        Returns:
            str: The answer's text.
        """
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
        """Publishes an event from this trader.

        Args:
            kind (event_module.EventKind): What happened.
            payload (dict): The event's details.
        """
        self._event_bus.publish(
            event_module.Event.now(kind, self.name, payload)
        )
