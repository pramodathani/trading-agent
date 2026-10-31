"""How full a trader's context window is, broken down by what fills it.

Claude Code measures its own window and names the categories itself, such as "Messages", "System tools" and "Free space". The Ollama and OpenAI backends have no such report, so their runner estimates the same kind of breakdown from the conversation it keeps: the system prompt, the tool definitions, the messages and the space left.

Typical usage example:

  usage = ContextUsage.estimate('qwen', 'qwen3.8:27b', 32768, conversation, definitions)
  usage.to_payload()
"""

import dataclasses
import datetime
import json
from collections.abc import Mapping, Sequence
from typing import Any

from trading_agent.agent import conversation as conversation_module

_CHARACTERS_PER_TOKEN = 3
_TOKENS_PER_IMAGE = 1500
SYSTEM_PROMPT = 'System prompt'
TOOLS = 'Tools'
MESSAGES = 'Messages'
FREE_SPACE = 'Free space'


@dataclasses.dataclass(frozen=True)
class ContextCategory:
    """One part of the context window.

    Attributes:
        name: What fills this part, such as "Messages".
        tokens: How many tokens it holds.
        deferred: True for something listed but not loaded into the window, such as a deferred tool.
    """

    name: str
    tokens: int
    deferred: bool = False


@dataclasses.dataclass(frozen=True)
class ContextUsage:
    """A snapshot of one backend's context window.

    Attributes:
        backend: The backend's name in trading_agent.toml.
        model: The model's name on its server.
        total_tokens: How many tokens the window holds.
        context_window: How many tokens it can hold.
        categories: What fills it, in the order to show them.
        measured: True when the model's own tool counted the tokens, False for an estimate.
        recorded_at: When the snapshot was taken, as ISO text.
    """

    backend: str
    model: str
    total_tokens: int
    context_window: int
    categories: tuple[ContextCategory, ...]
    measured: bool
    recorded_at: str

    @classmethod
    def from_claude(
        cls,
        backend: str,
        report: Mapping[str, Any],
    ) -> ContextUsage:
        """Builds a snapshot from Claude Code's get_context_usage report.

        Args:
            backend (str): The backend's name in trading_agent.toml.
            report (Mapping[str, Any]): The report, with categories, totalTokens, rawMaxTokens and model.

        Returns:
            ContextUsage: The snapshot.
        """
        categories = []
        for category in report.get('categories') or []:
            categories.append(
                ContextCategory(
                    name=str(category.get('name', '')),
                    tokens=int(category.get('tokens', 0)),
                    deferred=bool(category.get('isDeferred', False)),
                )
            )
        window = report.get('rawMaxTokens') or report.get('maxTokens') or 0
        return cls(
            backend=backend,
            model=str(report.get('model', '')),
            total_tokens=int(report.get('totalTokens', 0)),
            context_window=int(window),
            categories=tuple(categories),
            measured=True,
            recorded_at=cls._now_text(),
        )

    @classmethod
    def estimate(
        cls,
        backend: str,
        model: str,
        context_window: int,
        conversation: conversation_module.Conversation,
        tool_definitions: Sequence[Mapping[str, Any]],
    ) -> ContextUsage:
        """Estimates a snapshot from a conversation the agent loop keeps.

        The system prompt, the tool definitions and the messages are first counted roughly, at three characters per token and 1500 tokens per picture. Once the model has reported how many tokens it read, the three rough counts are scaled so that they add up to that total, because the rough rate is far off for some text, such as the JSON of tool definitions.

        Args:
            backend (str): The backend's name in trading_agent.toml.
            model (str): The model's name on its server.
            context_window (int): How many tokens the model is given.
            conversation (conversation_module.Conversation): The conversation so far.
            tool_definitions (Sequence[Mapping[str, Any]]): The tools the model is offered.

        Returns:
            ContextUsage: The estimated snapshot.
        """
        system_tokens = len(conversation.system_prompt) // _CHARACTERS_PER_TOKEN
        tool_tokens = (
            len(json.dumps(list(tool_definitions))) // _CHARACTERS_PER_TOKEN
        )
        message_tokens = cls._message_tokens(conversation)
        rough_total = system_tokens + tool_tokens + message_tokens
        total = rough_total
        if conversation.measured_tokens > 0 and rough_total > 0:
            total = conversation.estimated_tokens()
            system_tokens = round(system_tokens * total / rough_total)
            tool_tokens = round(tool_tokens * total / rough_total)
            message_tokens = max(0, total - system_tokens - tool_tokens)
        free = max(0, context_window - total)
        categories = (
            ContextCategory(SYSTEM_PROMPT, system_tokens),
            ContextCategory(TOOLS, tool_tokens),
            ContextCategory(MESSAGES, message_tokens),
            ContextCategory(FREE_SPACE, free),
        )
        return cls(
            backend=backend,
            model=model,
            total_tokens=total,
            context_window=context_window,
            categories=categories,
            measured=False,
            recorded_at=cls._now_text(),
        )

    def to_payload(self) -> dict[str, Any]:
        """Describes the snapshot for the gateway's API.

        Returns:
            dict[str, Any]: The snapshot as plain JSON-ready values.
        """
        categories = []
        for category in self.categories:
            categories.append(
                {
                    'name': category.name,
                    'tokens': category.tokens,
                    'deferred': category.deferred,
                }
            )
        return {
            'backend': self.backend,
            'model': self.model,
            'total_tokens': self.total_tokens,
            'context_window': self.context_window,
            'categories': categories,
            'measured': self.measured,
            'recorded_at': self.recorded_at,
        }

    @staticmethod
    def _message_tokens(conversation: conversation_module.Conversation) -> int:
        """Roughly counts the messages' tokens.

        Args:
            conversation (conversation_module.Conversation): The conversation.

        Returns:
            int: The estimate, at three characters per token and 1500 tokens per picture.
        """
        characters = 0
        pictures = 0
        for message in conversation.messages:
            characters += len(message.text)
            for call in message.tool_calls:
                characters += len(call.name) + len(str(call.arguments))
            pictures += len(message.images)
            if message.image is not None:
                pictures += 1
        return (
            characters // _CHARACTERS_PER_TOKEN + pictures * _TOKENS_PER_IMAGE
        )

    @staticmethod
    def _now_text() -> str:
        """The current time, for recorded_at.

        Returns:
            str: The time in UTC as ISO text.
        """
        return datetime.datetime.now(datetime.UTC).isoformat()
