"""Tests for side questions on the agent loop's runner, which must leave the conversation unchanged."""

import asyncio
from collections.abc import Callable
from typing import Any

from tests import fakes
from trading_agent.agent import agent_loop
from trading_agent.agent import agent_turn_runner
from trading_agent.agent import conversation as conversation_module
from trading_agent.agent import loop_guard
from trading_agent.agent import messages
from trading_agent.agent import prompt_builder
from trading_agent.backends import backend
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import turn_runner
from trading_agent.tools import tool_call_executor
from trading_agent.tools import tool_registry


class _RecordingBackend(backend.ModelBackend):
    """A backend that records what each call was given and answers with fixed text.

    Attributes:
        calls: For each call, the message texts and the number of tool definitions offered.
    """

    def __init__(self):
        """Creates the backend."""
        super().__init__('qwen', 'qwen3.8:27b')
        self.calls: list[tuple[list[str], int]] = []

    async def complete(
        self,
        conversation: conversation_module.Conversation,
        tool_definitions: list[dict[str, Any]],
        on_text: Callable[[str], None],
    ) -> backend.ModelReply:
        """Records the call and answers.

        Args:
            conversation (conversation_module.Conversation): The conversation sent.
            tool_definitions (list[dict[str, Any]]): The tools offered.
            on_text (Callable[[str], None]): Called with the answer.

        Returns:
            backend.ModelReply: "Because the trend turned."
        """
        texts = []
        for message in conversation.messages:
            texts.append(message.text)
        self.calls.append((texts, len(tool_definitions)))
        on_text('Because the trend turned.')
        return fakes.text_reply('Because the trend turned.')


class _FixedPromptBuilder:
    """Builds the same system prompt every time."""

    def build(self) -> prompt_builder.SystemPrompt:
        """Builds the prompt.

        Returns:
            prompt_builder.SystemPrompt: The prompt.
        """
        return prompt_builder.SystemPrompt(text='desk prompt', fingerprint='f')


class TestAgentSideQuestion:
    """Tests for AgentTurnRunner.side_question."""

    def test_question_sees_the_conversation_but_is_not_kept(self) -> None:
        """The model sees the conversation plus the question and no tools, and the desk's conversation is unchanged afterwards."""
        event_bus = event_bus_module.EventBus()
        model = _RecordingBackend()
        executor = tool_call_executor.ToolCallExecutor(
            'main',
            tool_registry.ToolRegistry(
                [
                    fakes.EchoTool(),
                ],
                5,
            ),
            event_bus,
            loop_guard.LoopGuard(maximum_identical_calls=2),
        )
        runner = agent_turn_runner.AgentTurnRunner(
            agent_loop.AgentLoop('main', model, executor, event_bus, 3),
            _FixedPromptBuilder(),
        )
        runner.conversation.append(
            messages.ConversationMessage.user('Sell INFY.')
        )
        runner.conversation.append(
            messages.ConversationMessage.assistant('Sold INFY.', [])
        )

        answer = asyncio.run(runner.side_question('Why?'))

        texts, tool_count = model.calls[0]
        assert answer == 'Because the trend turned.'
        assert texts[:2] == [
            'Sell INFY.',
            'Sold INFY.',
        ]
        assert texts[2] == f'{turn_runner.SIDE_QUESTION_NOTE}\nWhy?'
        assert tool_count == 0
        assert len(runner.conversation.messages) == 2
