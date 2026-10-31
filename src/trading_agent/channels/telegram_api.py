"""The one place that talks to Telegram's servers, through python-telegram-bot.

The bot asks Telegram for new messages with long polling: each request waits up to `poll_seconds` for a message and returns as soon as one arrives. The gateway therefore needs no open port and no public address; it only makes outgoing requests, like a browser.

Everything else in the Telegram channel talks to this class, so tests can replace it with a stand-in and never reach the internet.

Typical usage example:

  api = TelegramApi(token, poll_seconds=30)
  await api.start()
  messages = await api.messages()
  await api.send(chat_id, 'Hello')
  await api.send_photo(chat_id, Path('chart.png'), 'Today')
"""

import dataclasses
from collections.abc import Sequence
from pathlib import Path

import telegram
import telegram.error

_MESSAGE_LIMIT = 4000
_CAPTION_LIMIT = 1024
_EXTRA_READ_SECONDS = 10


class TelegramApiError(RuntimeError):
    """Telegram could not be reached or refused a request."""


@dataclasses.dataclass(frozen=True)
class IncomingFile:
    """A photo or file attached to a message, not yet downloaded.

    Attributes:
        file_id: Telegram's id for the file, used to download it.
        file_name: The file's name; a photo, which has none, gets one made from the message.
        size_bytes: The file's size as Telegram reports it, or 0 when unknown.
    """

    file_id: str
    file_name: str
    size_bytes: int


@dataclasses.dataclass(frozen=True)
class IncomingMessage:
    """One message sent to the bot: its text, and any photo or file with it.

    Attributes:
        chat_id: Telegram's id for the chat it came from.
        sender_name: The sender's first name, or their username when they have none.
        text: The message's text, or a photo's or file's caption; may be empty.
        files: The photo or file attached, not yet downloaded.
    """

    chat_id: int
    sender_name: str
    text: str
    files: tuple[IncomingFile, ...] = ()


@dataclasses.dataclass(frozen=True)
class IncomingButton:
    """A press on one of the bot's buttons.

    Attributes:
        chat_id: The chat the button's message is in.
        sender_name: The presser's first name, or their username when they have none.
        callback_id: Telegram's id for the press, used to acknowledge it.
        data: The text the bot attached to the button when sending it.
        message_id: The message that holds the button.
    """

    chat_id: int
    sender_name: str
    callback_id: str
    data: str
    message_id: int


ButtonRows = Sequence[Sequence[tuple[str, str]]]


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

    async def set_commands(self, commands: Sequence[tuple[str, str]]) -> None:
        """Sets the command menu Telegram shows when the user types a slash.

        Args:
            commands (Sequence[tuple[str, str]]): Each command as (name without the slash, description).

        Raises:
            TelegramApiError: Telegram could not be reached or refused the menu.
        """
        menu = []
        for name, description in commands:
            menu.append(telegram.BotCommand(name, description))
        try:
            await self._bot.set_my_commands(menu)
        except telegram.error.TelegramError as error:
            raise TelegramApiError(
                f'{type(error).__name__}: {error}'
            ) from error

    async def messages(self) -> list[IncomingMessage | IncomingButton]:
        """Waits for new messages and button presses, up to the poll time; stickers, voice notes and the like are skipped.

        Updates are acknowledged once returned, so each is returned only once.

        Returns:
            list[IncomingMessage | IncomingButton]: The new messages and presses, oldest first; empty when none arrived in time.

        Raises:
            TelegramApiError: Telegram could not be reached or refused the request.
        """
        try:
            updates = await self._bot.get_updates(
                offset=self._offset,
                timeout=self._poll_seconds,
                allowed_updates=[
                    'message',
                    'callback_query',
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
            press = update.callback_query
            if press is not None and press.message is not None:
                incoming.append(
                    IncomingButton(
                        chat_id=press.message.chat.id,
                        sender_name=press.from_user.first_name
                        or press.from_user.username
                        or '',
                        callback_id=press.id,
                        data=press.data or '',
                        message_id=press.message.message_id,
                    )
                )
                continue
            message = update.message
            if message is None:
                continue
            files = self._files(message)
            text = message.text or message.caption or ''
            if not text and not files:
                continue
            sender = message.from_user
            name = ''
            if sender is not None:
                name = sender.first_name or sender.username or ''
            incoming.append(
                IncomingMessage(
                    chat_id=message.chat.id,
                    sender_name=name,
                    text=text,
                    files=files,
                )
            )
        return incoming

    async def download(self, file_id: str) -> bytes:
        """Downloads a file that was sent to the bot.

        Telegram lets a bot download files of up to 20 MB.

        Args:
            file_id (str): Telegram's id for the file.

        Returns:
            bytes: The file's contents.

        Raises:
            TelegramApiError: Telegram could not be reached, or refused because the file is too large.
        """
        try:
            telegram_file = await self._bot.get_file(file_id)
            data = await telegram_file.download_as_bytearray()
        except telegram.error.TelegramError as error:
            raise TelegramApiError(
                f'{type(error).__name__}: {error}'
            ) from error
        return bytes(data)

    def _files(self, message: telegram.Message) -> tuple[IncomingFile, ...]:
        """The photo or file attached to a message.

        Telegram sends a photo in several sizes, smallest first; the largest is taken. A photo has no file name, so it is named after the message.

        Args:
            message (telegram.Message): The message.

        Returns:
            tuple[IncomingFile, ...]: The attached photo or file, or nothing.
        """
        if message.photo:
            largest = message.photo[-1]
            return (
                IncomingFile(
                    file_id=largest.file_id,
                    file_name=f'photo-{message.message_id}.jpg',
                    size_bytes=largest.file_size or 0,
                ),
            )
        if message.document is not None:
            document = message.document
            return (
                IncomingFile(
                    file_id=document.file_id,
                    file_name=document.file_name
                    or f'file-{message.message_id}',
                    size_bytes=document.file_size or 0,
                ),
            )
        return ()

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

    async def send_with_buttons(
        self,
        chat_id: int,
        text: str,
        rows: ButtonRows,
    ) -> int:
        """Sends a message with buttons under it; a text too long for one message is sent in parts, the buttons under the last.

        Args:
            chat_id (int): The chat.
            text (str): The message.
            rows (ButtonRows): The buttons, row by row, each a (label, data) pair; the data comes back when it is pressed.

        Returns:
            int: The id of the message holding the buttons.

        Raises:
            TelegramApiError: Telegram could not be reached or refused the message.
        """
        parts = self.parts(text)
        try:
            for part in parts[:-1]:
                await self._bot.send_message(chat_id, part)
            sent = await self._bot.send_message(
                chat_id,
                parts[-1],
                reply_markup=self._keyboard(rows),
            )
        except telegram.error.TelegramError as error:
            raise TelegramApiError(
                f'{type(error).__name__}: {error}'
            ) from error
        return sent.message_id

    async def edit(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        rows: ButtonRows | None,
    ) -> None:
        """Replaces the text and buttons of a message the bot sent.

        Args:
            chat_id (int): The chat.
            message_id (int): The message.
            text (str): The new text, cut to fit one message.
            rows (ButtonRows | None): The new buttons, or None to remove them.

        Raises:
            TelegramApiError: Telegram could not be reached or refused the change.
        """
        markup = None if rows is None else self._keyboard(rows)
        try:
            await self._bot.edit_message_text(
                text[:_MESSAGE_LIMIT],
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=markup,
            )
        except telegram.error.BadRequest as error:
            if 'not modified' in str(error).lower():
                return
            raise TelegramApiError(
                f'{type(error).__name__}: {error}'
            ) from error
        except telegram.error.TelegramError as error:
            raise TelegramApiError(
                f'{type(error).__name__}: {error}'
            ) from error

    async def acknowledge(self, callback_id: str, text: str = '') -> None:
        """Tells Telegram a button press was handled, optionally showing a short note on the phone.

        Args:
            callback_id (str): The press.
            text (str): A note of up to 200 characters, or empty for none.

        Raises:
            TelegramApiError: Telegram could not be reached or refused the request.
        """
        try:
            await self._bot.answer_callback_query(
                callback_id, text=text[:200] or None
            )
        except telegram.error.TelegramError as error:
            raise TelegramApiError(
                f'{type(error).__name__}: {error}'
            ) from error

    async def send_photo(self, chat_id: int, path: Path, caption: str) -> None:
        """Sends a picture with a caption.

        Telegram shows a photo inline but refuses one over 10 MB or with very long or thin proportions, such as a tall table; such a picture is sent as a file instead. A caption longer than Telegram allows follows as its own message.

        Args:
            chat_id (int): The chat.
            path (Path): The picture.
            caption (str): The text shown with it; may be empty.

        Raises:
            TelegramApiError: Telegram could not be reached or refused the picture both ways.
        """
        data = path.read_bytes()
        shown_caption = caption if len(caption) <= _CAPTION_LIMIT else ''
        try:
            await self._bot.send_photo(
                chat_id, data, caption=shown_caption or None
            )
        except telegram.error.BadRequest:
            try:
                await self._bot.send_document(
                    chat_id,
                    data,
                    filename=path.name,
                    caption=shown_caption or None,
                )
            except telegram.error.TelegramError as error:
                raise TelegramApiError(
                    f'{type(error).__name__}: {error}'
                ) from error
        except telegram.error.TelegramError as error:
            raise TelegramApiError(
                f'{type(error).__name__}: {error}'
            ) from error
        if caption and not shown_caption:
            await self.send(chat_id, caption)

    @staticmethod
    def _keyboard(rows: ButtonRows) -> telegram.InlineKeyboardMarkup:
        """Builds Telegram's buttons from (label, data) pairs.

        Args:
            rows (ButtonRows): The buttons, row by row.

        Returns:
            telegram.InlineKeyboardMarkup: The keyboard.
        """
        keyboard = []
        for row in rows:
            buttons = []
            for label, data in row:
                buttons.append(
                    telegram.InlineKeyboardButton(label, callback_data=data)
                )
            keyboard.append(buttons)
        return telegram.InlineKeyboardMarkup(keyboard)

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
