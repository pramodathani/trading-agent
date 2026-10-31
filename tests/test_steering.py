"""Tests for steering a running turn with a mid-turn message, and for /stop."""

import asyncio

from tests import fakes
from trading_agent.agent import agent_loop
from trading_agent.agent import conversation as conversation_module
from trading_agent.agent import loop_guard
from trading_agent.agent import messages
from trading_agent.backends import claude_steering_hook
from trading_agent.backends import model_router
from trading_agent.configuration import agent_configuration
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import steering_inbox as steering_inbox_module
from trading_agent.runtime import trader_runtime
from trading_agent.runtime import trigger as trigger_module
from trading_agent.runtime import turn_runner
from trading_agent.tools import tool
from trading_agent.tools import tool_call_executor
from trading_agent.tools import tool_registry

_STEERING_TEXT = 'Actually, only look at INFY.'


def _message(text: str) -> trigger_module.Trigger:
    """Builds a user message for the main trader.

    Args:
        text (str): The message.

    Returns:
        trigger_module.Trigger: The trigger.
    """
    return trigger_module.Trigger.now(
        trigger_module.TriggerSource.USER_MESSAGE,
        'main',
        text,
    )


class _MessageArrivesTool(tool.Tool):
    """A tool during which the user sends a message, as if typed while the tool ran."""

    name = 'scan'
    description = 'Scans the market.'

    def __init__(self, inbox: steering_inbox_module.SteeringInbox):
        """Creates the tool.

        Args:
            inbox (steering_inbox_module.SteeringInbox): The trader's steering inbox.
        """
        self._inbox = inbox

    async def run(self, arguments: tool.NoArguments) -> tool.ToolResult:
        """Puts the user's message in the inbox and finishes.

        Args:
            arguments (tool.NoArguments): No arguments.

        Returns:
            tool.ToolResult: A scan result.
        """
        del arguments
        self._inbox.add(_message(_STEERING_TEXT), 'running-turn')
        return tool.ToolResult.success('scanned 50 stocks')


class _WaitingTurnRunner(turn_runner.TurnRunner):
    """A turn runner whose first turn waits until it is released or cancelled.

    Attributes:
        started: Set when the first turn has started.
        release: Set by the test to let the first turn finish.
        texts: The text of every turn run, in order.
        side_release: Set by the test to let side questions finish; it starts set.
    """

    def __init__(self):
        """Creates the runner."""
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.texts: list[str] = []
        self.side_release = asyncio.Event()
        self.side_release.set()

    async def run_turn(
        self, trigger: trigger_module.Trigger
    ) -> turn_runner.TurnResult:
        """Waits on the first turn, and answers later turns at once.

        Args:
            trigger (trigger_module.Trigger): The reason for the turn.

        Returns:
            turn_runner.TurnResult: An echo of the message.
        """
        self.texts.append(trigger.text)
        if len(self.texts) == 1:
            self.started.set()
            await self.release.wait()
        return turn_runner.TurnResult(text='done')

    async def side_question(self, question: str) -> str:
        """Answers once side_release is set.

        Args:
            question (str): The question.

        Returns:
            str: "side: <question>".
        """
        await self.side_release.wait()
        return f'side: {question}'


class _TraderScenario:
    """A trader with a waiting turn runner, and every event it published."""

    def __init__(self, routed: bool = False):
        """Builds the trader.

        Args:
            routed (bool): True to put the runner behind a model router, as real traders have, which /btw needs.
        """
        self.event_bus = event_bus_module.EventBus()
        self.runner = _WaitingTurnRunner()
        trader_runner = self.runner
        if routed:
            trader_runner = model_router.ModelRouter(
                'main',
                [
                    model_router.BackendRoute('claude', self.runner),
                ],
                self.event_bus,
            )
        self.trader = trader_runtime.TraderRuntime(
            agent_configuration.TraderConfiguration(name='main'),
            self.event_bus,
            trader_runner,
        )
        self.events: list[event_module.Event] = []
        self.queued_while_busy = -1
        self.state_after = trader_runtime.TraderState.STOPPED

    async def collect(
        self,
        subscription: event_bus_module.EventSubscription,
        finished_turns: int,
    ) -> None:
        """Reads events until a number of turns have finished.

        Args:
            subscription (event_bus_module.EventSubscription): Where events arrive.
            finished_turns (int): How many turn_finished events to wait for.
        """
        seen = 0
        while seen < finished_turns:
            received = await asyncio.wait_for(
                subscription.next_event(), timeout=3
            )
            self.events.append(received)
            if received.kind == event_module.EventKind.TURN_FINISHED:
                seen += 1

    async def steer_then_finish(self) -> None:
        """Starts a turn, sends a message during it, then lets the turn end without a tool round."""
        with self.event_bus.subscribe() as subscription:
            task = asyncio.create_task(self.trader.run())
            self.trader.submit(_message('scan the market'))
            await self.runner.started.wait()
            self.trader.submit(_message(_STEERING_TEXT))
            self.queued_while_busy = self.trader.queued_count
            self.runner.release.set()
            await self.collect(subscription, 2)
            task.cancel()

    async def stop_running_turn(self, stop_text: str = '/stop') -> None:
        """Starts a turn that never ends by itself, and stops it with /stop.

        Args:
            stop_text (str): The stop message to send, such as "/stop now".
        """
        with self.event_bus.subscribe() as subscription:
            task = asyncio.create_task(self.trader.run())
            self.trader.submit(_message('think for a long time'))
            await self.runner.started.wait()
            self.trader.submit(_message(stop_text))
            await self.collect(subscription, 2)
            self.state_after = self.trader.state
            task.cancel()

    async def ask_during_turn(
        self, command: str, from_thread: bool = False
    ) -> None:
        """Starts a turn, sends a command while it runs, and waits for both answers, releasing the turn after the command's answer when the command was not queued.

        Args:
            command (str): The command to send, such as "/status".
            from_thread (bool): True to submit from a worker thread, as the gateway's web routes do.
        """
        with self.event_bus.subscribe() as subscription:
            task = asyncio.create_task(self.trader.run())
            self.trader.submit(_message('scan the market'))
            await self.runner.started.wait()
            if from_thread:
                await asyncio.to_thread(self.trader.submit, _message(command))
                await asyncio.sleep(0)
            else:
                self.trader.submit(_message(command))
            self.queued_while_busy = self.trader.queued_count
            finished_before_release = 0
            if self.queued_while_busy == 0:
                finished_before_release = 1
            await self.collect(subscription, finished_before_release)
            self.runner.release.set()
            await self.collect(subscription, 2 - finished_before_release)
            task.cancel()

    async def two_side_questions(self) -> None:
        """Sends two side questions while the first is held, then lets the first finish."""
        with self.event_bus.subscribe() as subscription:
            task = asyncio.create_task(self.trader.run())
            self.runner.side_release.clear()
            self.trader.submit(_message('/btw first'))
            await asyncio.sleep(0)
            self.trader.submit(_message('/btw second'))
            await self.collect(subscription, 1)
            self.runner.side_release.set()
            await self.collect(subscription, 1)
            task.cancel()

    def kinds(self) -> list[event_module.EventKind]:
        """The kinds of the collected events, in order.

        Returns:
            list[event_module.EventKind]: The kinds.
        """
        return [published.kind for published in self.events]

    def texts(self) -> list[str]:
        """The answers the trader published, in order.

        Returns:
            list[str]: The texts of the text events.
        """
        answers = []
        for published in self.events:
            if published.kind == event_module.EventKind.TEXT:
                answers.append(published.payload['text'])
        return answers


class _LoopHarness:
    """An agent loop with a steering inbox and a tool during which the user writes."""

    def __init__(self, replies: list):
        """Builds the loop.

        Args:
            replies (list): The scripted model's replies.
        """
        self.event_bus = event_bus_module.EventBus()
        self.inbox = steering_inbox_module.SteeringInbox(self.event_bus, 'main')
        self.backend = fakes.ScriptedBackend(replies)
        self.conversation = conversation_module.Conversation('test prompt')
        executor = tool_call_executor.ToolCallExecutor(
            'main',
            tool_registry.ToolRegistry(
                [
                    _MessageArrivesTool(self.inbox),
                    fakes.SlowTool(),
                ],
                timeout_seconds=30,
            ),
            self.event_bus,
            loop_guard.LoopGuard(maximum_identical_calls=3),
        )
        self.loop = agent_loop.AgentLoop(
            'main',
            self.backend,
            executor,
            self.event_bus,
            5,
            steering_inbox=self.inbox,
        )
        self.events: list[event_module.Event] = []

    async def run_turn(self) -> str:
        """Runs one turn and keeps its events.

        Returns:
            str: The final text.
        """
        with self.event_bus.subscribe() as subscription:
            result = await self.loop.run_turn(
                self.conversation, _message('scan the market')
            )
            while True:
                try:
                    self.events.append(subscription._queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
        return result.text

    async def cancel_during_tool(self) -> None:
        """Starts a turn whose tool never finishes, and cancels it while the tool runs."""
        task = asyncio.create_task(
            self.loop.run_turn(self.conversation, _message('wait'))
        )
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return


class TestSteering:
    """Tests for mid-turn messages."""

    def test_agent_loop_adds_the_message_before_the_next_model_call(
        self,
    ) -> None:
        """A message that arrives during a tool call is in the conversation the model sees next."""
        harness = _LoopHarness(
            [
                fakes.tool_reply('scan', {}),
                fakes.text_reply('Only INFY, then.'),
            ]
        )

        answer = asyncio.run(harness.run_turn())

        user_texts = [
            message.text
            for message in harness.conversation.messages
            if message.role == messages.Role.USER
        ]
        assert answer == 'Only INFY, then.'
        assert len(user_texts) == 2
        assert _STEERING_TEXT in user_texts[1]
        assert harness.backend.seen_message_counts == [
            1,
            4,
        ]
        steering = [
            published
            for published in harness.events
            if published.kind == event_module.EventKind.STEERING
        ]
        assert steering[0].payload['delivered'] is True

    def test_message_during_a_turn_is_not_queued(self) -> None:
        """A user message sent while a turn runs goes to the inbox, not the queue."""
        scenario = _TraderScenario()

        asyncio.run(scenario.steer_then_finish())

        assert scenario.queued_while_busy == 0
        received = [
            published
            for published in scenario.events
            if published.kind == event_module.EventKind.TRIGGER_RECEIVED
        ]
        assert 'steering_into' in received[1].payload

    def test_undelivered_message_becomes_its_own_turn(self) -> None:
        """A message the turn never picked up is run as the next turn, so it is not lost."""
        scenario = _TraderScenario()

        asyncio.run(scenario.steer_then_finish())

        assert len(scenario.runner.texts) == 2
        assert _STEERING_TEXT in scenario.runner.texts[1]
        steering = [
            published
            for published in scenario.events
            if published.kind == event_module.EventKind.STEERING
        ]
        assert steering[0].payload['delivered'] is False

    def test_commands_are_not_steering(self) -> None:
        """A slash command sent during a turn waits in the queue as before."""
        scenario = _TraderScenario()
        scenario.trader._running_trigger_id = 'running-turn'

        scenario.trader.submit(_message('/status'))

        assert scenario.trader.queued_count == 1

    def test_claude_hook_hands_over_waiting_messages(self) -> None:
        """The Claude hook returns waiting messages as additional context, once."""
        event_bus = event_bus_module.EventBus()
        inbox = steering_inbox_module.SteeringInbox(event_bus, 'main')
        hook = claude_steering_hook.ClaudeSteeringHook(inbox)
        inbox.add(_message(_STEERING_TEXT), 'running-turn')

        first = asyncio.run(hook({}, None, None))
        second = asyncio.run(hook({}, None, None))

        assert (
            _STEERING_TEXT in first['hookSpecificOutput']['additionalContext']
        )
        assert first['hookSpecificOutput']['hookEventName'] == 'PostToolUse'
        assert second == {}


class TestStop:
    """Tests for /stop."""

    def test_stop_cancels_the_running_turn(self) -> None:
        """/stop ends a turn that would otherwise never finish, and the trader is idle again."""
        scenario = _TraderScenario()

        asyncio.run(scenario.stop_running_turn())

        assert event_module.EventKind.STOPPED in scenario.kinds()
        assert 'Stopping the running turn.' in scenario.texts()
        assert any(
            text.startswith('Stopped by the user') for text in scenario.texts()
        )
        assert scenario.state_after == trader_runtime.TraderState.IDLE

    def test_stop_with_words_or_a_bot_name(self) -> None:
        """/stop followed by words, or with the @botname Telegram adds in groups, still stops the turn at once."""
        for stop_text in (
            '/stop now please',
            '/stop@test_bot',
        ):
            scenario = _TraderScenario()

            asyncio.run(scenario.stop_running_turn(stop_text))

            assert 'Stopping the running turn.' in scenario.texts()

    def test_stop_with_nothing_running(self) -> None:
        """/stop on an idle trader says there is nothing to stop and queues nothing."""
        scenario = _TraderScenario()

        scenario.trader.submit(_message('/stop'))

        assert scenario.trader.queued_count == 0

    def test_stopped_tool_call_gets_a_result(self) -> None:
        """A tool call cut short by /stop gets a result, so the next model call is valid."""
        harness = _LoopHarness(
            [
                fakes.tool_reply('slow', {}),
            ]
        )

        asyncio.run(harness.cancel_during_tool())

        last = harness.conversation.messages[-1]
        assert last.role == messages.Role.TOOL
        assert last.is_error
        assert '/stop' in last.text


class TestInstantCommands:
    """Tests for read-only commands answered beside the running turn."""

    def test_status_answers_while_a_turn_runs(self) -> None:
        """/status is answered before the running turn ends, and is not queued behind it."""
        scenario = _TraderScenario()

        asyncio.run(scenario.ask_during_turn('/status'))

        texts = scenario.texts()
        assert 'Trader: main' in texts[0]
        assert 'State: busy' in texts[0]
        assert texts[1] == 'done'
        assert scenario.queued_while_busy == 0
        assert scenario.runner.texts[-1].endswith('scan the market')

    def test_side_question_answers_while_a_turn_runs(self) -> None:
        """/btw is answered before the running turn ends, and is not queued behind it."""
        scenario = _TraderScenario(routed=True)

        asyncio.run(scenario.ask_during_turn('/btw how is it going?'))

        texts = scenario.texts()
        assert texts[0].startswith('Side answer from claude')
        assert texts[0].endswith('side: how is it going?')
        assert texts[1] == 'done'
        assert scenario.queued_while_busy == 0

    def test_one_side_question_at_a_time(self) -> None:
        """A second /btw while the first is still running is told to wait, and the first still gets its answer."""
        scenario = _TraderScenario(routed=True)

        asyncio.run(scenario.two_side_questions())

        texts = scenario.texts()
        assert (
            texts[0]
            == '/btw is still running. Wait for its answer, then ask again.'
        )
        assert texts[1].endswith('side: first')

    def test_status_from_a_web_route_thread_answers_at_once(self) -> None:
        """/status submitted from a worker thread, as a web route does, is handed to the trader's loop and still answered before the turn ends."""
        scenario = _TraderScenario()

        asyncio.run(scenario.ask_during_turn('/status', from_thread=True))

        texts = scenario.texts()
        assert 'State: busy' in texts[0]
        assert texts[1] == 'done'

    def test_changing_commands_still_wait_for_the_turn(self) -> None:
        """/new changes the trader, so it waits in the queue until the running turn ends."""
        scenario = _TraderScenario()

        asyncio.run(scenario.ask_during_turn('/new'))

        assert scenario.queued_while_busy == 1
        assert scenario.texts()[0] == 'done'


def test_inbox_is_empty_after_taking() -> None:
    """Taking the waiting messages empties the inbox."""
    inbox = steering_inbox_module.SteeringInbox(
        event_bus_module.EventBus(), 'main'
    )
    inbox.add(_message('one'), 'running-turn')

    assert inbox.take_text() is not None
    assert inbox.take_text() is None
    assert inbox.take_undelivered() == []
