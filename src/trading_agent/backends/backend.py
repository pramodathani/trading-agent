"""The base class for a model backend that answers one model call at a time.

The agent loop asks the backend for one reply, runs any tools the reply asks for, and asks again. The Ollama and OpenAI-compatible backends work this way. The Claude Code backend (milestone 3) runs the whole loop itself and has its own turn runner.

Typical usage example:

  reply = await backend.complete(conversation, registry.definitions(), on_text)
"""

import dataclasses
from collections.abc import Callable
from typing import Any

from trading_agent.agent import conversation as conversation_module
from trading_agent.agent import messages


class BackendUnavailableError(Exception):
    """The backend could not be reached or refused the request, so another backend should be tried."""


@dataclasses.dataclass(frozen=True)
class ModelReply:
    """One reply from the model.

    Attributes:
        text: The text the model wrote.
        tool_calls: The tools it asks to run.
        prompt_tokens: How many tokens the request used, or 0 when the server did not say.
        completion_tokens: How many tokens the reply used, or 0 when the server did not say.
    """

    text: str
    tool_calls: list[messages.ToolCall]
    prompt_tokens: int
    completion_tokens: int


class ModelBackend:
    """A backend the agent loop calls once per round. Subclasses do the actual call.

    Attributes:
        name: The backend's name in trading_agent.toml.
        model: The model's name on its server.
    """

    def __init__(self, name: str, model: str):
        """Creates the backend.

        Args:
            name (str): The backend's name in trading_agent.toml.
            model (str): The model's name on its server.
        """
        self.name = name
        self.model = model

    async def complete(
        self,
        conversation: conversation_module.Conversation,
        tool_definitions: list[dict[str, Any]],
        on_text: Callable[[str], None],
    ) -> ModelReply:
        """Asks the model for its next reply.

        Args:
            conversation (conversation_module.Conversation): The conversation so far.
            tool_definitions (list[dict[str, Any]]): The tools the model may call.
            on_text (Callable[[str], None]): Called with each piece of text as it streams in.

        Returns:
            ModelReply: The complete reply.

        Raises:
            NotImplementedError: Always, because subclasses must override this method.
        """
        raise NotImplementedError
