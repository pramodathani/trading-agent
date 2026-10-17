"""A backend that talks to a model on a local Ollama server.

It uses Ollama's own /api/chat endpoint through the `ollama` package, because only that endpoint lets each request set the context size (`num_ctx`) and turn thinking on or off.

Typical usage example:

  backend = OllamaBackend('gemma', backend_configuration)
  reply = await backend.complete(conversation, tool_definitions, on_text)
"""

from collections.abc import Callable
from typing import Any

import httpx
import ollama

from trading_agent.agent import conversation as conversation_module
from trading_agent.agent import messages
from trading_agent.backends import backend
from trading_agent.configuration import agent_configuration


class OllamaBackend(backend.ModelBackend):
    """One model on one Ollama server."""

    def __init__(
        self,
        name: str,
        backend_configuration: agent_configuration.BackendConfiguration,
    ):
        """Creates the backend without contacting the server.

        Args:
            name (str): The backend's name in trading_agent.toml.
            backend_configuration (agent_configuration.BackendConfiguration): Its settings, of kind "ollama".
        """
        super().__init__(name, backend_configuration.model)
        self._client = ollama.AsyncClient(host=backend_configuration.base_url)
        self._context_window = backend_configuration.context_window
        self._thinking = backend_configuration.thinking
        self._configured_thinking = backend_configuration.thinking

    def thinking(self) -> str | None:
        """Whether the model thinks before answering.

        Returns:
            str | None: "on" or "off".
        """
        if self._thinking:
            return 'on'
        return 'off'

    def set_thinking(self, level: str | None) -> bool:
        """Turns thinking off for "off", on for any other level, or back to trading_agent.toml for None.

        Ollama's thinking is on or off for most models, so the levels between low and max all mean on.

        Args:
            level (str | None): One of turn_runner.THINKING_LEVELS, or None for the configured setting.

        Returns:
            bool: Always True.
        """
        if level is None:
            self._thinking = self._configured_thinking
        else:
            self._thinking = level != 'off'
        return True

    async def complete(
        self,
        conversation: conversation_module.Conversation,
        tool_definitions: list[dict[str, Any]],
        on_text: Callable[[str], None],
    ) -> backend.ModelReply:
        """Streams one reply from Ollama.

        Args:
            conversation (conversation_module.Conversation): The conversation so far.
            tool_definitions (list[dict[str, Any]]): The tools the model may call.
            on_text (Callable[[str], None]): Called with each piece of text as it streams in.

        Returns:
            backend.ModelReply: The complete reply.

        Raises:
            backend.BackendUnavailableError: Ollama cannot be reached, or refused the request.
        """
        text_parts = []
        tool_calls = []
        prompt_tokens = 0
        completion_tokens = 0
        try:
            stream = await self._client.chat(
                model=self.model,
                messages=self._wire_messages(conversation),
                tools=tool_definitions,
                stream=True,
                think=self._thinking,
                options={
                    'num_ctx': self._context_window,
                },
            )
            async for chunk in stream:
                piece = chunk.message.content
                if piece:
                    text_parts.append(piece)
                    on_text(piece)
                for wire_call in chunk.message.tool_calls or []:
                    tool_calls.append(
                        messages.ToolCall.new(
                            wire_call.function.name,
                            dict(wire_call.function.arguments),
                        )
                    )
                if chunk.done:
                    prompt_tokens = chunk.prompt_eval_count or 0
                    completion_tokens = chunk.eval_count or 0
        except (
            ollama.ResponseError,
            httpx.HTTPError,
            ConnectionError,
        ) as error:
            raise backend.BackendUnavailableError(
                f'Ollama backend {self.name} failed: {error!r}'
            ) from error
        return backend.ModelReply(
            text=''.join(text_parts),
            tool_calls=tool_calls,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    def _wire_messages(
        self,
        conversation: conversation_module.Conversation,
    ) -> list[dict[str, Any]]:
        """Converts the conversation into Ollama's message format.

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
                wire_message = {
                    'role': 'tool',
                    'content': message.text,
                    'tool_name': message.tool_name,
                }
                if message.image is not None:
                    wire_message['images'] = [
                        message.image.base64_data(),
                    ]
                wire_messages.append(wire_message)
                continue
            wire_message = {
                'role': str(message.role),
                'content': message.text,
            }
            if message.images:
                encoded = []
                for image in message.images:
                    encoded.append(image.base64_data())
                wire_message['images'] = encoded
            if message.tool_calls:
                wire_calls = []
                for call in message.tool_calls:
                    wire_calls.append(
                        {
                            'function': {
                                'name': call.name,
                                'arguments': call.arguments,
                            },
                        }
                    )
                wire_message['tool_calls'] = wire_calls
            wire_messages.append(wire_message)
        return wire_messages
