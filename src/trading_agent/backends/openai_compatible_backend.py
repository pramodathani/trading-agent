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
_NO_VISION_NOTE = '[A picture was attached here, but this model cannot see pictures, so it was left out.]'


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
        self._vision = backend_configuration.vision
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
        reasoning_parts = []
        call_parts = {}
        usage = None
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
                    usage = chunk.usage
                for choice in chunk.choices:
                    thought = getattr(choice.delta, 'reasoning_content', None)
                    if thought:
                        reasoning_parts.append(thought)
                    piece = choice.delta.content
                    if piece:
                        text_parts.append(piece)
                        on_text(piece)
                    for delta_call in choice.delta.tool_calls or []:
                        self._add_call_delta(call_parts, delta_call)
        except openai.APIError as error:
            raise self._unavailable(error) from error
        tool_calls = []
        for index in sorted(call_parts):
            tool_calls.append(call_parts[index].to_tool_call())
        prompt_tokens = 0
        completion_tokens = 0
        cache_read_tokens = 0
        cost_usd = None
        if usage is not None:
            prompt_tokens = usage.prompt_tokens
            completion_tokens = usage.completion_tokens
            cache_read_tokens = self._cache_read_tokens(usage)
            cost_usd = self._cost_usd(usage, cache_read_tokens)
        return backend.ModelReply(
            text=''.join(text_parts),
            tool_calls=tool_calls,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            reasoning=''.join(reasoning_parts),
            cache_read_tokens=cache_read_tokens,
            cost_usd=cost_usd,
        )

    def _unavailable(
        self, error: openai.APIError
    ) -> backend.BackendUnavailableError:
        """Turns a failed request into the error that sends the router to the next backend.

        Subclasses override this to set a waiting time for errors they recognise, such as a server out of credit.

        Args:
            error (openai.APIError): The failure.

        Returns:
            backend.BackendUnavailableError: The error to raise.
        """
        return backend.BackendUnavailableError(
            f'OpenAI-compatible backend {self.name} failed: {error!r}'
        )

    def _cache_read_tokens(self, usage: Any) -> int:
        """How many prompt tokens the server read from its cache, as OpenAI reports it.

        Args:
            usage (Any): The completion's usage object.

        Returns:
            int: The cached tokens, or 0 when the server did not say.
        """
        details = getattr(usage, 'prompt_tokens_details', None)
        if details is None:
            return 0
        return int(getattr(details, 'cached_tokens', 0) or 0)

    def _cost_usd(self, usage: Any, cache_read_tokens: int) -> float | None:
        """What the call cost, when the backend knows its prices.

        Args:
            usage (Any): The completion's usage object.
            cache_read_tokens (int): The prompt tokens read from the cache.

        Returns:
            float | None: The cost in US dollars, or None; the plain backend leaves costs to the rupee prices in /usage.
        """
        del usage, cache_read_tokens
        return None

    def _assistant_extras(
        self, message: messages.ConversationMessage
    ) -> dict[str, Any]:
        """Extra fields sent with an assistant message, beyond its text and tool calls.

        Args:
            message (messages.ConversationMessage): The assistant message.

        Returns:
            dict[str, Any]: The fields; none for a plain OpenAI-compatible server.
        """
        del message
        return {}

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

    def _content(self, message: messages.ConversationMessage) -> Any:
        """A user or assistant message's content: its text, or its text and pictures.

        Args:
            message (messages.ConversationMessage): The message.

        Returns:
            Any: The text alone, or a list of a text part and one image part per picture.
        """
        if not message.images:
            return message.text
        if not self._vision:
            return f'{message.text}\n{_NO_VISION_NOTE}'.strip()
        content = [
            {
                'type': 'text',
                'text': message.text,
            },
        ]
        for image in message.images:
            content.append(
                {
                    'type': 'image_url',
                    'image_url': {
                        'url': f'data:{image.media_type};base64,{image.base64_data()}',
                    },
                }
            )
        return content

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
        pictures = []
        for message in conversation.messages:
            if message.role == messages.Role.TOOL:
                content = message.text
                if message.image is not None and not self._vision:
                    content += f'\n{_NO_VISION_NOTE}'
                elif message.image is not None:
                    content += '\n[The picture is in the next user message.]'
                    pictures.append(message)
                wire_messages.append(
                    {
                        'role': 'tool',
                        'tool_call_id': message.tool_call_id,
                        'content': content,
                    }
                )
                continue
            self._add_tool_pictures(wire_messages, pictures)
            pictures = []
            wire_message = {
                'role': str(message.role),
                'content': self._content(message),
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
            if message.role == messages.Role.ASSISTANT:
                wire_message.update(self._assistant_extras(message))
            wire_messages.append(wire_message)
        self._add_tool_pictures(wire_messages, pictures)
        return wire_messages

    def _add_tool_pictures(
        self,
        wire_messages: list[dict[str, Any]],
        tool_messages: list[messages.ConversationMessage],
    ) -> None:
        """Adds a user message holding the pictures that tools returned.

        Chat Completions takes only text in a tool message, so the pictures follow the tool results in a user message of their own.

        Args:
            wire_messages (list[dict[str, Any]]): The messages built so far; the new message is appended.
            tool_messages (list[messages.ConversationMessage]): The tool messages that returned a picture; nothing is added when it is empty.
        """
        if not tool_messages:
            return
        names = []
        for message in tool_messages:
            names.append(message.tool_name or 'a tool')
        content = [
            {
                'type': 'text',
                'text': f'[The pictures returned by the tool results above, in order: {", ".join(names)}.]',
            },
        ]
        for message in tool_messages:
            content.append(
                {
                    'type': 'image_url',
                    'image_url': {
                        'url': f'data:{message.image.media_type};base64,{message.image.base64_data()}',
                    },
                }
            )
        wire_messages.append(
            {
                'role': 'user',
                'content': content,
            }
        )
