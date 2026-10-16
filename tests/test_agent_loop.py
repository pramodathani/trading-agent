"""Tests for the agent loop, driven by a scripted model."""

import asyncio

from tests import fakes
from trading_agent.agent import agent_loop
from trading_agent.agent import conversation as conversation_module
from trading_agent.agent import loop_guard
from trading_agent.agent import messages
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.tools import tool_call_executor
from trading_agent.tools import tool_registry


class _Harness:
    """A loop, its conversation and every event it published.

    Attributes:
        backend: The scripted model.
        conversation: The conversation the turn appends to.
        events: Every event published during the turn.
    """

    def __init__(self, replies: list, maximum_rounds: int = 5):
        """Builds the loop around a scripted model.

        Args:
            replies (list): The scripted model's replies.
            maximum_rounds (int): The loop's round limit.
        """
        self.backend = fakes.ScriptedBackend(replies)
        self.conversation = conversation_module.Conversation('test prompt')
        self.events = []
        self._event_bus = event_bus_module.EventBus()
        executor = tool_call_executor.ToolCallExecutor(
            'main',
            tool_registry.ToolRegistry(
                [
                    fakes.EchoTool(),
                ],
                timeout_seconds=1,
            ),
            self._event_bus,
            loop_guard.LoopGuard(maximum_identical_calls=2),
        )
        self._loop = agent_loop.AgentLoop(
            'main',
            self.backend,
            executor,
            self._event_bus,
            maximum_rounds,
        )

    def run(self, text: str) -> str:
        """Runs one turn and collects its events.

        Args:
            text (str): The trigger's text.

        Returns:
            str: The turn's final text.
        """
        trigger = trigger_module.Trigger.now(
            trigger_module.TriggerSource.USER_MESSAGE,
            'main',
            text,
        )
        with self._event_bus.subscribe() as subscription:
            result = asyncio.run(
                self._loop.run_turn(self.conversation, trigger)
            )
            while True:
                try:
                    self.events.append(subscription._queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
        return result.text

    def kinds(self) -> list[event_module.EventKind]:
        """The kinds of the collected events, in order.

        Returns:
            list[event_module.EventKind]: The kinds.
        """
        return [published.kind for published in self.events]


class TestAgentLoop:
    """Tests for AgentLoop."""

    def test_plain_answer_ends_the_turn_in_one_round(self) -> None:
        """A reply without tool calls is the final answer."""
        harness = _Harness(
            [
                fakes.text_reply('Markets open at 09:15.'),
            ]
        )

        text = harness.run('When do markets open?')

        assert text == 'Markets open at 09:15.'
        assert harness.backend.seen_message_counts == [
            1,
        ]

    def test_tool_call_result_goes_back_to_the_model(self) -> None:
        """The loop runs a requested tool and asks the model again with the result."""
        harness = _Harness(
            [
                fakes.tool_reply(
                    'echo',
                    {
                        'word': 'reliance',
                    },
                ),
                fakes.text_reply('The tool said RELIANCE.'),
            ]
        )

        text = harness.run('Echo reliance')

        assert text == 'The tool said RELIANCE.'
        roles = [message.role for message in harness.conversation.messages]
        assert roles == [
            messages.Role.USER,
            messages.Role.ASSISTANT,
            messages.Role.TOOL,
            messages.Role.ASSISTANT,
        ]
        assert harness.conversation.messages[2].text == 'RELIANCE'

    def test_events_show_every_step(self) -> None:
        """A turn with one tool call publishes usage, the call, the result and streamed text."""
        harness = _Harness(
            [
                fakes.tool_reply(
                    'echo',
                    {
                        'word': 'tcs',
                    },
                ),
                fakes.text_reply('Done.'),
            ]
        )

        harness.run('Echo tcs')

        assert harness.kinds() == [
            event_module.EventKind.MODEL_USAGE,
            event_module.EventKind.TOOL_CALL,
            event_module.EventKind.TOOL_RESULT,
            event_module.EventKind.TEXT_DELTA,
            event_module.EventKind.TEXT_DELTA,
            event_module.EventKind.MODEL_USAGE,
        ]

    def test_round_limit_stops_a_model_that_never_answers(self) -> None:
        """A model that keeps calling tools is stopped at the round limit."""
        harness = _Harness(
            [
                fakes.tool_reply(
                    'echo',
                    {
                        'word': 'again',
                    },
                ),
            ],
            maximum_rounds=3,
        )

        text = harness.run('Loop forever')

        assert 'Stopped after 3 rounds' in text
        assert len(harness.backend.seen_message_counts) == 3

    def test_loop_guard_refuses_the_third_identical_call(self) -> None:
        """With a limit of two, the third identical call is refused instead of run."""
        harness = _Harness(
            [
                fakes.tool_reply(
                    'echo',
                    {
                        'word': 'same',
                    },
                ),
            ],
            maximum_rounds=3,
        )

        harness.run('Repeat yourself')

        tool_messages = [
            message
            for message in harness.conversation.messages
            if message.role == messages.Role.TOOL
        ]
        assert [message.is_error for message in tool_messages] == [
            False,
            False,
            True,
        ]
        assert 'Refused' in tool_messages[2].text

    def test_conversation_carries_over_to_the_next_turn(self) -> None:
        """A second turn sees the first turn's messages."""
        harness = _Harness(
            [
                fakes.text_reply('First answer.'),
            ]
        )

        harness.run('First question')
        harness.run('Second question')

        assert harness.backend.seen_message_counts == [
            1,
            3,
        ]
