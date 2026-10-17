"""Compresses a conversation into a summary when it fills too much of the model's context window.

A model can only read so many tokens at once: 32,768 for Gemma and Qwen as configured. When a conversation passes 70% of that, the agent loop first gives the desk a silent memory-flush turn to save what matters with add_note or Memory.md, and then this compressor asks the same model to summarise the older messages. The conversation starts again from that summary, followed by the current turn's messages, which are kept word for word.

If a single long turn passes 85% between tool rounds, the compressor runs at once without the flush, because Ollama would otherwise drop the oldest text, the instructions included, without saying so.

Typical usage example:

  compressor = ContextCompressor('main', 32768, 0.70, 0.85, event_bus)
  if compressor.is_full(conversation):
      await compressor.compress(conversation, backend, len(conversation.messages), 'threshold', trigger_id)
"""

import json
import logging

from trading_agent.agent import conversation as conversation_module
from trading_agent.agent import messages
from trading_agent.backends import backend as backend_module
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module

_LOGGER = logging.getLogger(__name__)
_CHARACTERS_PER_TOKEN = 3
_TRANSCRIPT_SHARE_OF_WINDOW = 0.5
_USER_TEXT_CHARACTERS = 4000
_ASSISTANT_TEXT_CHARACTERS = 4000
_ARGUMENT_CHARACTERS = 300
_RESULT_CHARACTERS = 1500
_SHORTENED_MARK = ' [… shortened for this summary; the desk saw the full text]'
FLUSH_REQUEST = "[Memory flush: your conversation is about to be compressed into a summary to free up context. Before it is, save anything you will need later that is not saved yet: record lessons with add_note, and put lasting facts in Memory.md. Do not place, change or cancel orders in this turn. Reply with one short line saying what you saved, or 'Nothing to save'.]"
SUMMARY_FOCUS = "open positions and orders with their ids, prices and quantities; the decisions made and why; the user's instructions and preferences; plans and pending tasks; errors and what was learned from them"
_SUMMARISER_PROMPT = f'You compress the conversation of a trading desk so it can continue in a smaller context. Write a factual summary in plain text, under 600 words, addressed to the desk as "you". Keep {SUMMARY_FOCUS}. Leave out greetings and anything finished that no longer matters. Never invent a number that is not in the transcript. Long tool results in the transcript were shortened only for this summary and are marked as shortened; the desk saw them in full at the time, so trust the answers it gave then and never report the shortening as missing or cut-off data.'


class ContextCompressor:
    """Decides when one backend's conversation is too full, and compresses it."""

    def __init__(
        self,
        desk_name: str,
        context_window: int,
        threshold: float,
        emergency_threshold: float,
        event_bus: event_bus_module.EventBus,
    ):
        """Creates the compressor.

        Args:
            desk_name (str): The desk, used to tag events.
            context_window (int): How many tokens the model is given.
            threshold (float): The share of the window at which to compress before a turn, such as 0.70.
            emergency_threshold (float): The share at which to compress in the middle of a turn, such as 0.85.
            event_bus (event_bus_module.EventBus): Where each compression is published.
        """
        self._desk_name = desk_name
        self._context_window = context_window
        self._threshold = threshold
        self._emergency_threshold = emergency_threshold
        self._event_bus = event_bus

    def is_full(self, conversation: conversation_module.Conversation) -> bool:
        """Says whether the conversation has reached the normal threshold.

        Args:
            conversation (conversation_module.Conversation): The conversation.

        Returns:
            bool: True when it should be compressed before the next turn.
        """
        limit = self._threshold * self._context_window
        return conversation.estimated_tokens() >= limit

    def is_overflowing(
        self,
        conversation: conversation_module.Conversation,
    ) -> bool:
        """Says whether the conversation has reached the emergency threshold.

        Args:
            conversation (conversation_module.Conversation): The conversation.

        Returns:
            bool: True when it must be compressed before the next model call.
        """
        limit = self._emergency_threshold * self._context_window
        return conversation.estimated_tokens() >= limit

    async def compress(
        self,
        conversation: conversation_module.Conversation,
        backend: backend_module.ModelBackend,
        keep_from: int,
        reason: str,
        trigger_id: str,
    ) -> bool:
        """Summarises the messages before keep_from and restarts the conversation from the summary.

        Args:
            conversation (conversation_module.Conversation): The conversation to compress.
            backend (backend_module.ModelBackend): The model that writes the summary.
            keep_from (int): The index of the first message to keep word for word, normally the current turn's user message.
            reason (str): "threshold", "emergency" or "command", for the event.
            trigger_id (str): The trigger of the turn that caused it, for the event.

        Returns:
            bool: True when the conversation was compressed, False when there was nothing older to summarise.

        Raises:
            backend_module.BackendUnavailableError: The model could not write the summary.
        """
        earlier = conversation.messages[:keep_from]
        kept = conversation.messages[keep_from:]
        if not earlier:
            return False
        tokens_before = conversation.estimated_tokens()
        summary = await self._summary(earlier, backend)
        share = round(100 * tokens_before / self._context_window)
        block = '\n'.join(
            [
                f'[Your earlier conversation was compressed because it filled about {share}% of your context window. Your notes and Memory.md hold what you chose to keep, and search_sessions finds the full record. Summary of the earlier conversation:]',
                summary,
                '[End of the summary.]',
            ]
        )
        conversation.restart(
            [
                messages.ConversationMessage.user(block),
                *kept,
            ]
        )
        self._event_bus.publish(
            event_module.Event.now(
                event_module.EventKind.CONTEXT_COMPRESSED,
                self._desk_name,
                {
                    'trigger_id': trigger_id,
                    'backend': backend.name,
                    'reason': reason,
                    'tokens_before': tokens_before,
                    'context_window': self._context_window,
                    'messages_summarised': len(earlier),
                    'messages_kept': len(kept),
                    'summary_characters': len(summary),
                },
            )
        )
        return True

    async def _summary(
        self,
        earlier: tuple[messages.ConversationMessage, ...],
        backend: backend_module.ModelBackend,
    ) -> str:
        """Asks the model, with no tools, to summarise a transcript of the earlier messages.

        Args:
            earlier (tuple[messages.ConversationMessage, ...]): The messages to summarise.
            backend (backend_module.ModelBackend): The model.

        Returns:
            str: The summary, or the transcript's newest part when the model wrote nothing.
        """
        transcript = self._transcript(earlier)
        request = conversation_module.Conversation(_SUMMARISER_PROMPT)
        request.append(
            messages.ConversationMessage.user(
                f'Summarise this conversation:\n\n{transcript}'
            )
        )
        reply = await backend.complete(request, [], self._ignore_text)
        if reply.text.strip():
            return reply.text.strip()
        _LOGGER.warning(
            'The model wrote an empty summary for desk %s', self._desk_name
        )
        return transcript[-_RESULT_CHARACTERS * 4 :]

    def _transcript(
        self,
        earlier: tuple[messages.ConversationMessage, ...],
    ) -> str:
        """Writes the messages out as plain text, newest kept when it is too long.

        The first message is always kept, because after an earlier compression it holds the previous summary.

        Args:
            earlier (tuple[messages.ConversationMessage, ...]): The messages.

        Returns:
            str: The transcript, fitting in half the context window.
        """
        budget = int(
            self._context_window
            * _TRANSCRIPT_SHARE_OF_WINDOW
            * _CHARACTERS_PER_TOKEN
        )
        blocks = []
        for message in earlier:
            blocks.append(self._render(message))
        first = blocks[0][:budget]
        used = len(first)
        newest = []
        for block in reversed(blocks[1:]):
            if used + len(block) > budget:
                newest.append('[… older messages left out …]')
                break
            newest.append(block)
            used += len(block)
        newest.reverse()
        return '\n\n'.join([first, *newest])

    def _render(self, message: messages.ConversationMessage) -> str:
        """Writes one message as plain text, shortening long parts.

        Args:
            message (messages.ConversationMessage): The message.

        Returns:
            str: The text.
        """
        if message.role == messages.Role.USER:
            pictures = ''
            if message.images:
                pictures = f' [with {len(message.images)} picture(s)]'
            return f'Message to you{pictures}: {self._shorten(message.text, _USER_TEXT_CHARACTERS)}'
        if message.role == messages.Role.TOOL:
            outcome = 'failed' if message.is_error else 'returned'
            pictures = ''
            if message.image is not None:
                pictures = ' a picture and'
            return f'Tool {message.tool_name} {outcome}{pictures}: {self._shorten(message.text, _RESULT_CHARACTERS)}'
        lines = []
        if message.text:
            lines.append(
                f'You: {self._shorten(message.text, _ASSISTANT_TEXT_CHARACTERS)}'
            )
        for call in message.tool_calls:
            arguments = json.dumps(call.arguments, ensure_ascii=False)
            lines.append(
                f'You called {call.name}({self._shorten(arguments, _ARGUMENT_CHARACTERS)})'
            )
        return '\n'.join(lines)

    def _shorten(self, text: str, limit: int) -> str:
        """Cuts text to a length, marking the cut.

        Args:
            text (str): The text.
            limit (int): The most characters to keep.

        Returns:
            str: The text, marked as shortened when it was cut.
        """
        if len(text) <= limit:
            return text
        return text[:limit] + _SHORTENED_MARK

    def _ignore_text(self, piece: str) -> None:
        """Drops the summary's streamed pieces, which are not shown to anyone.

        Args:
            piece (str): A piece of the summary.
        """
        del piece
