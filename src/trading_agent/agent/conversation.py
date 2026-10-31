"""A trader's conversation with its model: the system prompt and the messages so far.

Messages are appended, and only ever changed in two ways: compression replaces the whole history at once with a summary and the current turn, which is a fresh conversation as far as the model can tell, and older pictures are taken out so that only the newest few are sent with every model call.

The conversation also remembers how many tokens the model said it held at the last call, so the compressor can tell how full the context window is.

Typical usage example:

  conversation = Conversation('You are a trader.')
  conversation.append(ConversationMessage.user('Hello'))
"""

import dataclasses
from collections.abc import Sequence

from trading_agent.agent import messages

_CHARACTERS_PER_TOKEN = 3
_TOKENS_PER_IMAGE = 1500
_PICTURE_REMOVED_NOTE = '[The picture that was here has been taken out of the conversation to save room. If a saved path is given above, view_image shows it again.]'


class Conversation:
    """An append-only list of messages with a fixed system prompt.

    Attributes:
        system_prompt: The instructions sent before every message.
        measured_tokens: The tokens the model reported for the conversation at its last call, or 0 before any call.
    """

    def __init__(self, system_prompt: str):
        """Creates an empty conversation.

        Args:
            system_prompt (str): The instructions sent before every message.
        """
        self.system_prompt = system_prompt
        self.measured_tokens = 0
        self._measured_message_count = 0
        self._messages = []

    def append(self, message: messages.ConversationMessage) -> None:
        """Adds a message to the end.

        Args:
            message (messages.ConversationMessage): The message to add.
        """
        self._messages.append(message)

    def copy(self) -> Conversation:
        """A separate conversation with the same prompt and messages, which can be extended without changing this one.

        Returns:
            Conversation: The copy.
        """
        duplicate = Conversation(self.system_prompt)
        duplicate.measured_tokens = self.measured_tokens
        duplicate._measured_message_count = self._measured_message_count
        duplicate._messages = list(self._messages)
        return duplicate

    @property
    def messages(self) -> tuple[messages.ConversationMessage, ...]:
        """The messages so far, oldest first, as a read-only tuple."""
        return tuple(self._messages)

    def record_usage(self, tokens: int) -> None:
        """Remembers how many tokens the model reported at the call that just finished.

        Args:
            tokens (int): The prompt tokens plus the reply's tokens.
        """
        self.measured_tokens = tokens
        self._measured_message_count = len(self._messages)

    def estimated_tokens(self) -> int:
        """How many tokens the next call will send, as closely as can be told now.

        It is the last measured count plus an estimate for the messages added since, such as tool results: three characters per token of text, and 1500 tokens for each picture.

        Returns:
            int: The estimate.
        """
        added_characters = 0
        added_images = 0
        for message in self._messages[self._measured_message_count :]:
            added_characters += len(message.text)
            for call in message.tool_calls:
                added_characters += len(call.name) + len(str(call.arguments))
            added_images += len(message.images)
            if message.image is not None:
                added_images += 1
        return (
            self.measured_tokens
            + added_characters // _CHARACTERS_PER_TOKEN
            + added_images * _TOKENS_PER_IMAGE
        )

    def keep_newest_pictures(self, count: int) -> int:
        """Takes every picture but the newest few out of the conversation, leaving a note in each one's place.

        Every message is sent again with each model call, so a picture left in the history costs about 1500 tokens on every later call.

        Args:
            count (int): How many of the newest pictures to keep.

        Returns:
            int: How many pictures were taken out.
        """
        seen = 0
        removed = 0
        for index in range(len(self._messages) - 1, -1, -1):
            message = self._messages[index]
            pictures = len(message.images)
            if message.image is not None:
                pictures += 1
            if pictures == 0:
                continue
            seen += pictures
            if seen - pictures >= count:
                self._messages[index] = self._without_pictures(message)
                removed += pictures
        return removed

    def _without_pictures(
        self,
        message: messages.ConversationMessage,
    ) -> messages.ConversationMessage:
        """Makes a copy of a message with its pictures replaced by a note.

        A message is kept whole or emptied of pictures, never split, so the newest pictures may number a little more than asked.

        Args:
            message (messages.ConversationMessage): The message.

        Returns:
            messages.ConversationMessage: The copy.
        """
        return dataclasses.replace(
            message,
            text=f'{message.text}\n{_PICTURE_REMOVED_NOTE}'.strip(),
            image=None,
            images=(),
        )

    def restart(
        self,
        new_messages: Sequence[messages.ConversationMessage],
    ) -> None:
        """Replaces the whole history at once, for compression.

        Args:
            new_messages (Sequence[messages.ConversationMessage]): The messages the conversation starts again with.
        """
        self._messages = list(new_messages)
        self.measured_tokens = 0
        self._measured_message_count = 0
