"""Tests for compressing a conversation when it fills the model's context window."""

import asyncio
from collections.abc import Callable
from typing import Any

import pydantic
import pytest

from tests import fakes
from trading_agent.agent import agent_loop
from trading_agent.agent import agent_turn_runner
from trading_agent.agent import context_compressor
from trading_agent.agent import conversation as conversation_module
from trading_agent.agent import loop_guard
from trading_agent.agent import messages
from trading_agent.agent import prompt_builder
from trading_agent.backends import backend
from trading_agent.backends import claude_pre_compact_hook
from trading_agent.configuration import agent_configuration
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.tools import tool_call_executor
from trading_agent.tools import tool_registry

_WINDOW = 1000
_SUMMARY = 'You bought 1 IDEA at 12.21.'


class _RecordingBackend(backend.ModelBackend):
    """A backend that answers summary requests with a fixed summary and other calls from a script.

    Attributes:
        calls: For each call, a tuple (system prompt, last message text, number of tools offered).
    """

    def __init__(self, replies: list[backend.ModelReply]):
        """Creates the backend.

        Args:
            replies (list[backend.ModelReply]): The replies to non-summary calls, in order; the last one repeats.
        """
        super().__init__('gemma', 'gemma-test')
        self._replies = replies
        self._reply_count = 0
        self.calls = []

    async def complete(
        self,
        conversation: conversation_module.Conversation,
        tool_definitions: list[dict[str, Any]],
        on_text: Callable[[str], None],
    ) -> backend.ModelReply:
        """Records the call and replies.

        Args:
            conversation (conversation_module.Conversation): The conversation sent.
            tool_definitions (list[dict[str, Any]]): The tools offered.
            on_text (Callable[[str], None]): Ignored.

        Returns:
            backend.ModelReply: The summary for a summary request, otherwise the next scripted reply.
        """
        del on_text
        last_text = conversation.messages[-1].text
        self.calls.append(
            (
                conversation.system_prompt,
                last_text,
                len(tool_definitions),
            )
        )
        if last_text.startswith('Summarise this conversation'):
            return fakes.text_reply(_SUMMARY)
        index = min(self._reply_count, len(self._replies) - 1)
        self._reply_count += 1
        return self._replies[index]


def _reply(
    text: str,
    prompt_tokens: int,
    tool_name: str | None = None,
) -> backend.ModelReply:
    """Builds a reply that reports a given prompt size.

    Args:
        text (str): The reply's text.
        prompt_tokens (int): The prompt size the server reports.
        tool_name (str | None): A tool to call, or None.

    Returns:
        backend.ModelReply: The reply.
    """
    calls = []
    if tool_name is not None:
        calls.append(
            messages.ToolCall.new(
                tool_name,
                {
                    'word': 'hi',
                },
            )
        )
    return backend.ModelReply(
        text=text,
        tool_calls=calls,
        prompt_tokens=prompt_tokens,
        completion_tokens=10,
    )


class _FixedPromptBuilder:
    """Stands in for the prompt builder with a fixed prompt."""

    def build(self) -> prompt_builder.SystemPrompt:
        """Returns the fixed prompt.

        Returns:
            prompt_builder.SystemPrompt: The prompt "rules".
        """
        return prompt_builder.SystemPrompt(text='rules', fingerprint='f')


class _EventReader:
    """Reads every event already published to a subscription."""

    def __init__(self, subscription: event_bus_module.EventSubscription):
        """Creates the reader.

        Args:
            subscription (event_bus_module.EventSubscription): The subscription to read.
        """
        self._subscription = subscription

    def kinds(self) -> list[event_module.EventKind]:
        """Takes the waiting events off the subscription.

        Returns:
            list[event_module.EventKind]: Their kinds, oldest first.
        """
        return [published.kind for published in asyncio.run(self._drain())]

    async def _drain(self) -> list[event_module.Event]:
        """Collects events until none arrives for a moment.

        Returns:
            list[event_module.Event]: The events.
        """
        events = []
        while True:
            try:
                events.append(
                    await asyncio.wait_for(
                        self._subscription.next_event(), 0.01
                    )
                )
            except TimeoutError:
                return events


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
    """An agent loop with a compressor over a 1,000-token window.

    Attributes:
        event_bus: The bus.
        backend: The recording backend.
        loop: The loop.
        conversation: A conversation that already holds one exchange.
    """

    def __init__(self, replies: list[backend.ModelReply]):
        """Builds the loop.

        Args:
            replies (list[backend.ModelReply]): The backend's scripted replies.
        """
        self.event_bus = event_bus_module.EventBus()
        self.backend = _RecordingBackend(replies)
        executor = tool_call_executor.ToolCallExecutor(
            'main',
            tool_registry.ToolRegistry(
                [
                    fakes.EchoTool(),
                ],
                timeout_seconds=1,
            ),
            self.event_bus,
            loop_guard.LoopGuard(maximum_identical_calls=3),
        )
        self.loop = agent_loop.AgentLoop(
            'main',
            self.backend,
            executor,
            self.event_bus,
            maximum_rounds=5,
            compressor=context_compressor.ContextCompressor(
                'main',
                _WINDOW,
                0.70,
                0.85,
                self.event_bus,
            ),
        )
        self.conversation = conversation_module.Conversation('rules')
        self.conversation.append(messages.ConversationMessage.user('Buy IDEA?'))
        self.conversation.append(
            messages.ConversationMessage.assistant('Bought 1 IDEA.', [])
        )


class TestConversationSize:
    """The conversation tracks how full it is."""

    def test_estimate_adds_messages_after_the_last_measurement(self) -> None:
        """New messages add about one token per three characters."""
        conversation = conversation_module.Conversation('rules')
        conversation.append(messages.ConversationMessage.user('hello'))
        conversation.record_usage(500)
        conversation.append(messages.ConversationMessage.user('x' * 300))
        assert conversation.estimated_tokens() == 600

    def test_restart_replaces_history_and_forgets_the_measurement(
        self,
    ) -> None:
        """After a restart only the new messages count."""
        conversation = conversation_module.Conversation('rules')
        conversation.append(messages.ConversationMessage.user('old'))
        conversation.record_usage(900)
        conversation.restart(
            [
                messages.ConversationMessage.user('abc'),
            ]
        )
        assert [message.text for message in conversation.messages] == [
            'abc',
        ]
        assert conversation.estimated_tokens() == 1


class TestCompressionBeforeATurn:
    """At 70% the trader flushes its memory, then the conversation is summarised."""

    def test_full_conversation_is_flushed_then_summarised(self) -> None:
        """The flush turn comes first, then a tool-less summary call, then the trigger on a fresh conversation."""
        setup = _Setup(
            [
                _reply('Nothing to save', 300),
                _reply('Done.', 300),
            ]
        )
        setup.conversation.record_usage(750)
        subscription = setup.event_bus.subscribe()

        result = asyncio.run(
            setup.loop.run_turn(setup.conversation, _trigger('What now?'))
        )

        assert result.text == 'Done.'
        flush_call, summary_call, turn_call = setup.backend.calls
        assert flush_call[1] == context_compressor.FLUSH_REQUEST
        assert flush_call[2] == 1
        assert summary_call[2] == 0
        assert 'Message to you: Buy IDEA?' in summary_call[1]
        assert 'You: Bought 1 IDEA.' in summary_call[1]
        assert turn_call[1] == 'What now?'
        texts = [message.text for message in setup.conversation.messages]
        assert texts[0].startswith('[Your earlier conversation was compressed')
        assert _SUMMARY in texts[0]
        assert texts[1:] == [
            'What now?',
            'Done.',
        ]
        kinds = _EventReader(subscription).kinds()
        assert event_module.EventKind.CONTEXT_COMPRESSED in kinds

    def test_conversation_below_the_threshold_is_left_alone(self) -> None:
        """At 50% nothing is flushed or summarised."""
        setup = _Setup(
            [
                _reply('Done.', 300),
            ]
        )
        setup.conversation.record_usage(500)
        asyncio.run(
            setup.loop.run_turn(setup.conversation, _trigger('What now?'))
        )
        assert len(setup.backend.calls) == 1
        assert setup.conversation.messages[0].text == 'Buy IDEA?'


class TestEmergencyCompression:
    """Past 85% in the middle of a turn, the conversation is compressed at once."""

    def test_long_turn_is_compressed_between_tool_rounds(self) -> None:
        """The current turn's messages are kept word for word after the summary."""
        setup = _Setup(
            [
                _reply('', 900, tool_name='echo'),
                _reply('Done.', 400),
            ]
        )
        setup.conversation.record_usage(100)

        asyncio.run(
            setup.loop.run_turn(setup.conversation, _trigger('Check IDEA'))
        )

        assert setup.backend.calls[1][1].startswith(
            'Summarise this conversation'
        )
        assert context_compressor.FLUSH_REQUEST not in [
            call[1] for call in setup.backend.calls
        ]
        conversation_messages = setup.conversation.messages
        assert _SUMMARY in conversation_messages[0].text
        assert conversation_messages[1].text == 'Check IDEA'
        assert conversation_messages[2].tool_calls[0].name == 'echo'
        assert conversation_messages[3].text == 'HI'
        assert conversation_messages[4].text == 'Done.'


class TestCompactCommand:
    """/compact flushes and compresses on request."""

    def test_compact_compresses_and_reports(self) -> None:
        """The agent turn runner compresses and says from how many tokens."""
        setup = _Setup(
            [
                _reply('Saved one note.', 300),
            ]
        )
        runner = agent_turn_runner.AgentTurnRunner(
            setup.loop,
            _FixedPromptBuilder(),
        )
        runner.conversation = setup.conversation
        setup.conversation.record_usage(200)

        reply = asyncio.run(runner.compact(_trigger('/compact')))

        assert reply.startswith('Compressed the conversation from about 200')
        assert _SUMMARY in runner.conversation.messages[0].text


class TestTranscript:
    """The transcript sent for summarising fits in half the window."""

    def test_first_and_newest_messages_are_kept(self) -> None:
        """The previous summary and the newest messages survive; the middle is left out."""
        compressor = context_compressor.ContextCompressor(
            'main',
            _WINDOW,
            0.70,
            0.85,
            event_bus_module.EventBus(),
        )
        earlier = [
            messages.ConversationMessage.user('previous summary'),
        ]
        for index in range(20):
            earlier.append(
                messages.ConversationMessage.user(f'{index:02d} ' + 'x' * 200)
            )
        transcript = compressor._transcript(tuple(earlier))
        assert transcript.startswith('Message to you: previous summary')
        assert '[… older messages left out …]' in transcript
        assert '19 ' in transcript
        assert '00 ' not in transcript
        assert len(transcript) <= 1500 + 200

    def test_long_tool_result_is_marked_as_shortened(self) -> None:
        """A cut tool result says the cut was made for the summary, so it is not mistaken for missing data."""
        compressor = context_compressor.ContextCompressor(
            'main',
            _WINDOW,
            0.70,
            0.85,
            event_bus_module.EventBus(),
        )
        call = messages.ToolCall.new('get_candles', {})
        text = compressor._render(
            messages.ConversationMessage.tool_result(call, 'x' * 2000, False)
        )
        assert text.startswith('Tool get_candles returned: ')
        assert text.endswith(
            '[… shortened for this summary; the trader saw the full text]'
        )


class TestClaudePreCompactHook:
    """The hook tells the runner about every compaction and publishes the automatic ones."""

    def test_automatic_compaction_is_published_and_manual_is_not(
        self,
    ) -> None:
        """Both call back; only "auto" publishes an event."""
        event_bus = event_bus_module.EventBus()
        subscription = event_bus.subscribe()
        calls = []
        hook = claude_pre_compact_hook.ClaudePreCompactHook(
            'main',
            'claude',
            event_bus,
            lambda: calls.append('compacted'),
        )
        asyncio.run(
            hook(
                {
                    'trigger': 'manual',
                },
                None,
                None,
            )
        )
        result = asyncio.run(
            hook(
                {
                    'trigger': 'auto',
                },
                None,
                None,
            )
        )
        assert result == {}
        assert calls == [
            'compacted',
            'compacted',
        ]
        assert _EventReader(subscription).kinds() == [
            event_module.EventKind.CONTEXT_COMPRESSED,
        ]


class TestCompressionSettings:
    """The thresholds are checked when the configuration is read."""

    def test_emergency_threshold_must_be_above_the_normal_one(self) -> None:
        """0.70 and 0.60 is refused."""
        with pytest.raises(pydantic.ValidationError):
            agent_configuration.AgentLoopConfiguration(
                compression_threshold=0.70,
                emergency_compression_threshold=0.60,
            )
