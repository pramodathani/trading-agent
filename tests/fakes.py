"""Stand-ins for models and tools, so the agent loop can be tested without a GPU."""

import asyncio
from collections.abc import Callable
from typing import Any

import pydantic

from trading_agent.agent import conversation as conversation_module
from trading_agent.agent import messages
from trading_agent.backends import backend
from trading_agent.tools import tool


class ScriptedBackend(backend.ModelBackend):
    """A backend that replies with a fixed list of replies, one per call.

    Attributes:
        seen_message_counts: How many messages the conversation held at each call.
    """

    def __init__(self, replies: list[backend.ModelReply]):
        """Creates the backend.

        Args:
            replies (list[backend.ModelReply]): The replies to give, in order; the last one repeats.
        """
        super().__init__('scripted', 'scripted-model')
        self._replies = replies
        self._call_count = 0
        self.seen_message_counts = []

    async def complete(
        self,
        conversation: conversation_module.Conversation,
        tool_definitions: list[dict[str, Any]],
        on_text: Callable[[str], None],
    ) -> backend.ModelReply:
        """Returns the next scripted reply, streaming its text in two pieces.

        Args:
            conversation (conversation_module.Conversation): The conversation so far.
            tool_definitions (list[dict[str, Any]]): The tools offered, ignored.
            on_text (Callable[[str], None]): Called with the reply's text in two halves.

        Returns:
            backend.ModelReply: The next reply.
        """
        del tool_definitions
        self.seen_message_counts.append(len(conversation.messages))
        index = min(self._call_count, len(self._replies) - 1)
        self._call_count += 1
        reply = self._replies[index]
        if reply.text:
            middle = len(reply.text) // 2
            on_text(reply.text[:middle])
            on_text(reply.text[middle:])
        return reply


def text_reply(text: str) -> backend.ModelReply:
    """Builds a reply that only has text.

    Args:
        text (str): The text.

    Returns:
        backend.ModelReply: The reply.
    """
    return backend.ModelReply(
        text=text,
        tool_calls=[],
        prompt_tokens=10,
        completion_tokens=5,
    )


def tool_reply(name: str, arguments: dict[str, Any]) -> backend.ModelReply:
    """Builds a reply that asks for one tool call.

    Args:
        name (str): The tool's name.
        arguments (dict[str, Any]): Its arguments.

    Returns:
        backend.ModelReply: The reply.
    """
    return backend.ModelReply(
        text='',
        tool_calls=[
            messages.ToolCall.new(name, arguments),
        ],
        prompt_tokens=10,
        completion_tokens=5,
    )


class EchoArguments(pydantic.BaseModel):
    """The arguments of EchoTool.

    Attributes:
        word: The word to echo back.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    word: str


class EchoTool(tool.Tool):
    """A tool that returns its argument in capitals."""

    name = 'echo'
    description = 'Returns the word in capitals.'
    arguments_model = EchoArguments

    async def run(self, arguments: EchoArguments) -> tool.ToolResult:
        """Echoes the word.

        Args:
            arguments (EchoArguments): The word.

        Returns:
            tool.ToolResult: The word in capitals.
        """
        return tool.ToolResult.success(arguments.word.upper())


class CrashingTool(tool.Tool):
    """A tool that always raises."""

    name = 'crash'
    description = 'Always fails.'

    async def run(self, arguments: tool.NoArguments) -> tool.ToolResult:
        """Raises.

        Args:
            arguments (tool.NoArguments): No arguments.

        Raises:
            RuntimeError: Always.
        """
        del arguments
        raise RuntimeError('broken tool')


class SlowTool(tool.Tool):
    """A tool that takes longer than any test timeout."""

    name = 'slow'
    description = 'Sleeps for a long time.'

    async def run(self, arguments: tool.NoArguments) -> tool.ToolResult:
        """Sleeps for ten seconds.

        Args:
            arguments (tool.NoArguments): No arguments.

        Returns:
            tool.ToolResult: Never reached within a test's timeout.
        """
        del arguments
        await asyncio.sleep(10)
        return tool.ToolResult.success('finished')


class LongOutputTool(tool.Tool):
    """A tool whose output is longer than the registry allows."""

    name = 'long'
    description = 'Returns a very long text.'

    async def run(self, arguments: tool.NoArguments) -> tool.ToolResult:
        """Returns fifty thousand characters.

        Args:
            arguments (tool.NoArguments): No arguments.

        Returns:
            tool.ToolResult: The long text.
        """
        del arguments
        return tool.ToolResult.success('x' * 50000)
