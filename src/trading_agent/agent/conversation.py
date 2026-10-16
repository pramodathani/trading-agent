"""A desk's conversation with its model: the system prompt and the messages so far.

Messages are only ever appended, never edited, because Claude's preserved-thinking check rejects a history that was changed after the fact. Compression (milestone 12) starts a new conversation instead of editing this one.

Typical usage example:

  conversation = Conversation('You are a trading desk.')
  conversation.append(ConversationMessage.user('Hello'))
"""

from trading_agent.agent import messages


class Conversation:
    """An append-only list of messages with a fixed system prompt.

    Attributes:
        system_prompt: The instructions sent before every message.
    """

    def __init__(self, system_prompt: str):
        """Creates an empty conversation.

        Args:
            system_prompt (str): The instructions sent before every message.
        """
        self.system_prompt = system_prompt
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
