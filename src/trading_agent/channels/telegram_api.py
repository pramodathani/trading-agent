"""The one place that talks to Telegram's servers, through python-telegram-bot.

The bot asks Telegram for new messages with long polling: each request waits up to `poll_seconds` for a message and returns as soon as one arrives. The gateway therefore needs no open port and no public address; it only makes outgoing requests, like a browser.

Everything else in the Telegram channel talks to this class, so tests can replace it with a stand-in and never reach the internet.

Typical usage example:

  api = TelegramApi(token, poll_seconds=30)
  await api.start()
  messages = await api.messages()
  await api.send(chat_id, 'Hello')
"""

import dataclasses

import telegram
import telegram.error

_MESSAGE_LIMIT = 4000
_EXTRA_READ_SECONDS = 10


class TelegramApiError(RuntimeError):
    """Telegram could not be reached or refused a request."""


@dataclasses.dataclass(frozen=True)
class IncomingMessage:
    """One text message sent to the bot.

    Attributes:
        chat_id: Telegram's id for the chat it came from.
        sender_name: The sender's first name, or their username when they have none.
        text: The message's text.
    """

    chat_id: int
    sender_name: str
    text: str


class TelegramApi:
    """The bot's connection to Telegram."""

    def __init__(self, token: str, poll_seconds: int):
        """Creates the connection without contacting Telegram.

        Args:
            token (str): The bot token from BotFather.
            poll_seconds (int): How long one long-poll request waits for messages.
        """
        self._bot = telegram.Bot(token)
        self._poll_seconds = poll_seconds
        self._offset: int | None = None
        self.username = ''

    async def start(self) -> str:
        """Checks the token and learns the bot's username.

        Returns:
            str: The bot's username, such as my_trading_agent_bot.

        Raises:
            TelegramApiError: The token is wrong or Telegram cannot be reached.
        """
        try:
            await self._bot.initialize()
            me = await self._bot.get_me()
        except telegram.error.TelegramError as error:
            raise TelegramApiError(
                f'{type(error).__name__}: {error}'
            ) from error
        self.username = me.username or ''
        return self.username

    async def messages(self) -> list[IncomingMessage]:
        """Waits for new text messages, up to the poll time.

        Messages are acknowledged once returned, so each is returned only once.

        Returns:
            list[IncomingMessage]: The new messages, oldest first; empty when none arrived in time.

        Raises:
            TelegramApiError: Telegram could not be reached or refused the request.
        """
        try:
            updates = await self._bot.get_updates(
                offset=self._offset,
                timeout=self._poll_seconds,
                allowed_updates=[
                    'message',
                ],
                read_timeout=self._poll_seconds + _EXTRA_READ_SECONDS,
            )
        except telegram.error.TelegramError as error:
            raise TelegramApiError(
                f'{type(error).__name__}: {error}'
            ) from error
        incoming = []
        for update in updates:
            self._offset = update.update_id + 1
            message = update.message
            if message is None or message.text is None:
                continue
            sender = message.from_user
            name = ''
            if sender is not None:
                name = sender.first_name or sender.username or ''
            incoming.append(
                IncomingMessage(
                    chat_id=message.chat.id,
                    sender_name=name,
                    text=message.text,
                )
            )
        return incoming

    async def send(self, chat_id: int, text: str) -> None:
        """Sends a plain-text message, split into parts when it is longer than Telegram allows.

        Args:
            chat_id (int): The chat.
            text (str): The message.

        Raises:
            TelegramApiError: Telegram could not be reached or refused the message.
        """
        for part in self.parts(text):
            try:
                await self._bot.send_message(chat_id, part)
            except telegram.error.TelegramError as error:
                raise TelegramApiError(
                    f'{type(error).__name__}: {error}'
                ) from error

    async def close(self) -> None:
        """Closes the connection."""
        try:
            await self._bot.shutdown()
        except telegram.error.TelegramError:
            return

    @staticmethod
    def parts(text: str) -> list[str]:
        """Splits a long message at line breaks into parts Telegram accepts.

        Args:
            text (str): The message.

        Returns:
            list[str]: The parts, each at most 4000 characters; one part for a short message.
        """
        text = text.strip() or '(empty)'
        parts = []
        current = ''
        for line in text.split('\n'):
            while len(line) > _MESSAGE_LIMIT:
                if current:
                    parts.append(current)
                    current = ''
                parts.append(line[:_MESSAGE_LIMIT])
                line = line[_MESSAGE_LIMIT:]
            if len(current) + len(line) + 1 > _MESSAGE_LIMIT:
                parts.append(current)
                current = line
            elif current:
                current = f'{current}\n{line}'
            else:
                current = line
        if current:
            parts.append(current)
        return parts
