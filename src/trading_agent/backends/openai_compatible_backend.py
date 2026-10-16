"""A backend for OpenAI, or any server that speaks OpenAI's Chat Completions protocol.

That covers OpenAI itself and local servers such as vLLM, LM Studio and llama.cpp. Tool calls stream in pieces: the arguments arrive as fragments of a JSON string, which are joined and parsed once the reply is complete.

Typical usage example:

  backend = OpenAICompatibleBackend('openai', backend_configuration, api_key)
  reply = await backend.complete(conversation, tool_definitions, on_text)
"""

import json
from collections.abc import Callable
from typing import Any

import openai

from trading_agent.agent import conversation as conversation_module
from trading_agent.agent import messages
from trading_agent.backends import backend
from trading_agent.configuration import agent_configuration

_INVALID_ARGUMENTS_KEY = 'unparseable_arguments'
_PLACEHOLDER_API_KEY = 'not-needed'


class _ToolCallParts:
    """The pieces of one streamed tool call, joined as they arrive.

    Attributes:
        call_id: The call's identifier from the server.
        name: The tool's name.
        argument_fragments: The pieces of the arguments' JSON text.
    """

    def __init__(self):
        """Creates an empty set of parts."""
        self.call_id = ''
        self.name = ''
        self.argument_fragments = []

    def to_tool_call(self) -> messages.ToolCall:
        """Joins the parts into a tool call.

        Arguments that are not valid JSON are kept as text under a key no tool accepts, so the registry refuses the call and shows the model what it wrote.

        Returns:
            messages.ToolCall: The call.
        """
        text = ''.join(self.argument_fragments) or '{}'
        try:
            arguments = json.loads(text)
        except json.JSONDecodeError:
            arguments = {
                _INVALID_ARGUMENTS_KEY: text,
            }
        if not isinstance(arguments, dict):
            arguments = {
                _INVALID_ARGUMENTS_KEY: text,
            }
        call_id = self.call_id or messages.ToolCall.new(self.name, {}).call_id
        return messages.ToolCall(
            call_id=call_id,
            name=self.name,
            arguments=arguments,
        )


class OpenAICompatibleBackend(backend.ModelBackend):
    """One model on one OpenAI-compatible server."""

    def __init__(
        self,
        name: str,
        backend_configuration: agent_configuration.BackendConfiguration,
        api_key: str,
    ):
        """Creates the backend without contacting the server.

        Args:
            name (str): The backend's name in trading_agent.toml.
            backend_configuration (agent_configuration.BackendConfiguration): Its settings, of kind "openai_compatible".
            api_key (str): The server's API key, or an empty string for a local server that needs none.
        """
        super().__init__(name, backend_configuration.model)
        self._client = openai.AsyncOpenAI(
            base_url=backend_configuration.base_url,
            api_key=api_key or _PLACEHOLDER_API_KEY,
            max_retries=0,
        )

    async def complete(
        self,
        conversation: conversation_module.Conversation,
        tool_definitions: list[dict[str, Any]],
        on_text: Callable[[str], None],
    ) -> backend.ModelReply:
        """Streams one reply from the server.

        Args:
            conversation (conversation_module.Conversation): The conversation so far.
            tool_definitions (list[dict[str, Any]]): The tools the model may call.
            on_text (Callable[[str], None]): Called with each piece of text as it streams in.

        Returns:
            backend.ModelReply: The complete reply.

        Raises:
            backend.BackendUnavailableError: The server cannot be reached, refused the request, or is rate limiting.
        """
        text_parts = []
        call_parts = {}
        prompt_tokens = 0
        completion_tokens = 0
        try:
            stream = await self._client.chat.completions.create(
                model=self.model,
                messages=self._wire_messages(conversation),
                tools=tool_definitions or openai.omit,
                stream=True,
                stream_options={
                    'include_usage': True,
                },
            )
            async for chunk in stream:
                if chunk.usage is not None:
                    prompt_tokens = chunk.usage.prompt_tokens
                    completion_tokens = chunk.usage.completion_tokens
                for choice in chunk.choices:
                    piece = choice.delta.content
                    if piece:
                        text_parts.append(piece)
                        on_text(piece)
                    for delta_call in choice.delta.tool_calls or []:
                        self._add_call_delta(call_parts, delta_call)
        except openai.APIError as error:
            raise backend.BackendUnavailableError(
                f'OpenAI-compatible backend {self.name} failed: {error!r}'
            ) from error
        tool_calls = []
        for index in sorted(call_parts):
            tool_calls.append(call_parts[index].to_tool_call())
        return backend.ModelReply(
            text=''.join(text_parts),
            tool_calls=tool_calls,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    def _add_call_delta(
        self,
        call_parts: dict[int, _ToolCallParts],
        delta_call: Any,
    ) -> None:
        """Adds one streamed piece of a tool call to its parts.

        Args:
            call_parts (dict[int, _ToolCallParts]): The parts so far, keyed by the call's index in the reply.
            delta_call (Any): One ChoiceDeltaToolCall from the stream.
        """
        parts = call_parts.setdefault(delta_call.index, _ToolCallParts())
        if delta_call.id:
            parts.call_id = delta_call.id
        if delta_call.function is None:
            return
        if delta_call.function.name:
            parts.name += delta_call.function.name
        if delta_call.function.arguments:
            parts.argument_fragments.append(delta_call.function.arguments)

    def _wire_messages(
        self,
        conversation: conversation_module.Conversation,
    ) -> list[dict[str, Any]]:
        """Converts the conversation into the Chat Completions message format.

        Args:
            conversation (conversation_module.Conversation): The conversation.

        Returns:
            list[dict[str, Any]]: The system prompt followed by every message.
        """
        wire_messages = [
            {
                'role': 'system',
                'content': conversation.system_prompt,
            },
        ]
        for message in conversation.messages:
            if message.role == messages.Role.TOOL:
                wire_messages.append(
                    {
                        'role': 'tool',
                        'tool_call_id': message.tool_call_id,
                        'content': message.text,
                    }
                )
                continue
            wire_message = {
                'role': str(message.role),
                'content': message.text,
            }
            if message.tool_calls:
                wire_calls = []
                for call in message.tool_calls:
                    wire_calls.append(
                        {
                            'id': call.call_id,
                            'type': 'function',
                            'function': {
                                'name': call.name,
                                'arguments': json.dumps(call.arguments),
                            },
                        }
                    )
                wire_message['tool_calls'] = wire_calls
            wire_messages.append(wire_message)
        return wire_messages
