"""The messages of a conversation, in a form that does not depend on any model.

Each backend converts these into its own wire format, so the same conversation can move from Gemma to Qwen to Claude when the router changes backend.

Typical usage example:

  call = ToolCall.new('get_time', {})
  message = ConversationMessage.assistant('', [call])
"""

import dataclasses
import enum
import uuid
from typing import Any, Self


class Role(enum.StrEnum):
    """Who a message comes from."""

    USER = 'user'
    ASSISTANT = 'assistant'
    TOOL = 'tool'


@dataclasses.dataclass(frozen=True)
class ToolCall:
    """One request from the model to run a tool.

    Attributes:
        call_id: An identifier that matches the call with its result. Ollama gives none, so it is created here when missing.
        name: The tool's name.
        arguments: The arguments, as the model wrote them.
    """

    call_id: str
    name: str
    arguments: dict[str, Any]

    @classmethod
    def new(cls, name: str, arguments: dict[str, Any]) -> Self:
        """Creates a tool call with a fresh identifier.

        Args:
            name (str): The tool's name.
            arguments (dict[str, Any]): The arguments.

        Returns:
            ToolCall: The new call.
        """
        return cls(call_id=uuid.uuid4().hex, name=name, arguments=arguments)


@dataclasses.dataclass(frozen=True)
class ConversationMessage:
    """One message in a conversation.

    Attributes:
        role: Who the message comes from.
        text: The message's text; may be empty for an assistant message that only calls tools.
        tool_calls: The tools an assistant message asks to run.
        tool_call_id: For a tool message, the identifier of the call it answers.
        tool_name: For a tool message, the name of the tool that ran.
        is_error: For a tool message, whether the tool failed.
        image_png: For a tool message, a picture the tool returned, or None.
    """

    role: Role
    text: str
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None
    tool_name: str | None = None
    is_error: bool = False
    image_png: bytes | None = None

    @classmethod
    def user(cls, text: str) -> Self:
        """Creates a user message.

        Args:
            text (str): What the user, or a trigger, says.

        Returns:
            ConversationMessage: The message.
        """
        return cls(role=Role.USER, text=text)

    @classmethod
    def assistant(cls, text: str, tool_calls: list[ToolCall]) -> Self:
        """Creates an assistant message.

        Args:
            text (str): The model's text.
            tool_calls (list[ToolCall]): The tools it asks to run.

        Returns:
            ConversationMessage: The message.
        """
        return cls(role=Role.ASSISTANT, text=text, tool_calls=tuple(tool_calls))

    @classmethod
    def tool_result(
        cls,
        call: ToolCall,
        text: str,
        is_error: bool,
        image_png: bytes | None = None,
    ) -> Self:
        """Creates the message that carries a tool's result back to the model.

        Args:
            call (ToolCall): The call being answered.
            text (str): The tool's output.
            is_error (bool): Whether the tool failed.
            image_png (bytes | None): A picture the tool returned, or None.

        Returns:
            ConversationMessage: The message.
        """
        return cls(
            role=Role.TOOL,
            text=text,
            tool_call_id=call.call_id,
            tool_name=call.name,
            is_error=is_error,
            image_png=image_png,
        )
