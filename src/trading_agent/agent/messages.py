"""The messages of a conversation, in a form that does not depend on any model.

Each backend converts these into its own wire format, so the same conversation can move from Gemma to Qwen to Claude when the router changes backend.

Typical usage example:

  call = ToolCall.new('get_time', {})
  message = ConversationMessage.assistant('', [call])
"""

import base64
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
class MessageImage:
    """A picture sent to the model, with a user message or a tool's result.

    Attributes:
        media_type: The picture's media type, image/jpeg or image/png.
        data: The encoded picture.
    """

    media_type: str
    data: bytes

    def base64_data(self) -> str:
        """The picture in base64, as the model APIs take it.

        Returns:
            str: The base64 text.
        """
        return base64.b64encode(self.data).decode('ascii')


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
        image: For a tool message, a picture the tool returned, or None.
        images: For a user message, the pictures sent with it.
        reasoning: For an assistant message, the model's visible thinking, which some servers, such as DeepSeek's, require to be sent back with the message.
    """

    role: Role
    text: str
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None
    tool_name: str | None = None
    is_error: bool = False
    image: MessageImage | None = None
    images: tuple[MessageImage, ...] = ()
    reasoning: str = ''

    @classmethod
    def user(
        cls,
        text: str,
        images: tuple[MessageImage, ...] = (),
    ) -> Self:
        """Creates a user message.

        Args:
            text (str): What the user, or a trigger, says.
            images (tuple[MessageImage, ...]): The pictures sent with it.

        Returns:
            ConversationMessage: The message.
        """
        return cls(role=Role.USER, text=text, images=images)

    @classmethod
    def assistant(
        cls,
        text: str,
        tool_calls: list[ToolCall],
        reasoning: str = '',
    ) -> Self:
        """Creates an assistant message.

        Args:
            text (str): The model's text.
            tool_calls (list[ToolCall]): The tools it asks to run.
            reasoning (str): The model's visible thinking, or empty.

        Returns:
            ConversationMessage: The message.
        """
        return cls(
            role=Role.ASSISTANT,
            text=text,
            tool_calls=tuple(tool_calls),
            reasoning=reasoning,
        )

    @classmethod
    def tool_result(
        cls,
        call: ToolCall,
        text: str,
        is_error: bool,
        image: MessageImage | None = None,
    ) -> Self:
        """Creates the message that carries a tool's result back to the model.

        Args:
            call (ToolCall): The call being answered.
            text (str): The tool's output.
            is_error (bool): Whether the tool failed.
            image (MessageImage | None): A picture the tool returned, or None.

        Returns:
            ConversationMessage: The message.
        """
        return cls(
            role=Role.TOOL,
            text=text,
            tool_call_id=call.call_id,
            tool_name=call.name,
            is_error=is_error,
            image=image,
        )
