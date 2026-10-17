"""A desk's conversation with its model: the system prompt and the messages so far.

Messages are only ever appended, never edited one by one. Compression replaces the whole history at once with a summary and the current turn, which is a fresh conversation as far as the model can tell.

The conversation also remembers how many tokens the model said it held at the last call, so the compressor can tell how full the context window is.

Typical usage example:

  conversation = Conversation('You are a trading desk.')
  conversation.append(ConversationMessage.user('Hello'))
"""

from collections.abc import Sequence

from trading_agent.agent import messages

_CHARACTERS_PER_TOKEN = 3
_TOKENS_PER_IMAGE = 1500


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
            if message.image_png is not None:
                added_images += 1
        return (
            self.measured_tokens
            + added_characters // _CHARACTERS_PER_TOKEN
            + added_images * _TOKENS_PER_IMAGE
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
