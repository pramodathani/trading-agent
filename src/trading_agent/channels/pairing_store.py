"""Which Telegram chats may command the traders, and the pairing codes waiting for the user's approval.

Anyone who finds the bot can message it, so the bot obeys only chats the user has approved. A chat that is not paired gets an eight-character code. The user approves the code in the web page or with `trading-agent pairing approve`, which proves the chat is theirs: only someone who can see the bot's reply and reach this machine can do both. A code expires after an hour.

The store is one JSON file in workspace/shared, which the traders can read but never write, so no trader can pair a chat by itself. The file is read afresh for every question, so an approval made by the command line reaches the running gateway at once.

Typical usage example:

  store = PairingStore(layout.telegram_pairing_file)
  code = store.request(chat_id, 'Pramod')
  store.approve(code)
  store.is_paired(chat_id)
"""

import dataclasses
import datetime
import json
import logging
import os
import secrets
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)
_CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
_CODE_LENGTH = 8
_CODE_LIFETIME = datetime.timedelta(hours=1)
_MOST_PENDING = 5


class PairingError(ValueError):
    """A pairing code that does not exist or has expired, or a chat that is not paired."""


@dataclasses.dataclass(frozen=True)
class PendingPairing:
    """A chat waiting for the user to approve its code.

    Attributes:
        code: The eight-character code the bot sent to the chat.
        chat_id: Telegram's id for the chat.
        name: The sender's name, as Telegram gives it.
        requested_at: When the code was made, as an ISO 8601 string in UTC.
    """

    code: str
    chat_id: int
    name: str
    requested_at: str


@dataclasses.dataclass(frozen=True)
class PairedChat:
    """A chat the traders obey.

    Attributes:
        chat_id: Telegram's id for the chat.
        name: The sender's name when it was paired.
        paired_at: When it was approved, as an ISO 8601 string in UTC.
        trader: The trader the chat talks to.
    """

    chat_id: int
    name: str
    paired_at: str
    trader: str


class PairingStore:
    """The paired chats and pending codes, kept in one JSON file."""

    def __init__(
        self, path: Path, clock: Callable[[], datetime.datetime] | None = None
    ):
        """Creates the store without reading the file.

        Args:
            path (Path): The JSON file.
            clock (Callable[[], datetime.datetime] | None): Returns the current time in UTC; None uses the system clock.
        """
        self._path = path
        self._clock = clock
        self._lock = threading.Lock()

    def request(self, chat_id: int, name: str) -> str | None:
        """Gives an unpaired chat a pairing code, reusing its code while it is still valid.

        Args:
            chat_id (int): The chat.
            name (str): The sender's name.

        Returns:
            str | None: The code, or None when too many codes are already waiting, so strangers cannot fill the list.
        """
        with self._lock:
            data = self._read_live()
            for pending in data['pending']:
                if pending['chat_id'] == chat_id:
                    return pending['code']
            if len(data['pending']) >= _MOST_PENDING:
                return None
            code = self._new_code()
            data['pending'].append(
                dataclasses.asdict(
                    PendingPairing(
                        code=code,
                        chat_id=chat_id,
                        name=name,
                        requested_at=self._now().isoformat(timespec='seconds'),
                    )
                )
            )
            self._write(data)
            return code

    def approve(self, code: str, trader: str) -> PairedChat:
        """Pairs the chat that was given a code.

        Args:
            code (str): The code, with or without a dash, in any case.
            trader (str): The trader the chat starts talking to.

        Returns:
            PairedChat: The newly paired chat.

        Raises:
            PairingError: No valid code matches.
        """
        wanted = code.replace('-', '').replace(' ', '').upper()
        with self._lock:
            data = self._read_live()
            for pending in data['pending']:
                if pending['code'] == wanted:
                    data['pending'].remove(pending)
                    chat = PairedChat(
                        chat_id=pending['chat_id'],
                        name=pending['name'],
                        paired_at=self._now().isoformat(timespec='seconds'),
                        trader=trader,
                    )
                    data['paired'] = [
                        entry
                        for entry in data['paired']
                        if entry['chat_id'] != chat.chat_id
                    ]
                    data['paired'].append(dataclasses.asdict(chat))
                    self._write(data)
                    return chat
        raise PairingError(
            f'No pairing code {wanted!r} is waiting; codes expire after an hour'
        )

    def revoke(self, chat_id: int) -> PairedChat:
        """Unpairs a chat, so the traders stop obeying it.

        Args:
            chat_id (int): The chat.

        Returns:
            PairedChat: The chat that was removed.

        Raises:
            PairingError: The chat is not paired.
        """
        with self._lock:
            data = self._read_live()
            for entry in data['paired']:
                if entry['chat_id'] == chat_id:
                    data['paired'].remove(entry)
                    self._write(data)
                    return PairedChat(**entry)
        raise PairingError(f'Chat {chat_id} is not paired')

    def paired_chat(self, chat_id: int) -> PairedChat | None:
        """Finds a paired chat.

        Args:
            chat_id (int): The chat.

        Returns:
            PairedChat | None: The chat, or None when it is not paired.
        """
        for chat in self.paired_chats():
            if chat.chat_id == chat_id:
                return chat
        return None

    def paired_chats(self) -> list[PairedChat]:
        """Every paired chat.

        Returns:
            list[PairedChat]: The chats, in the order they were paired.
        """
        with self._lock:
            data = self._read_live()
        chats = []
        for entry in data['paired']:
            chats.append(PairedChat(**entry))
        return chats

    def pending(self) -> list[PendingPairing]:
        """Every code still waiting for approval.

        Returns:
            list[PendingPairing]: The codes, oldest first.
        """
        with self._lock:
            data = self._read_live()
        pending = []
        for entry in data['pending']:
            pending.append(PendingPairing(**entry))
        return pending

    def choose_trader(self, chat_id: int, trader: str) -> None:
        """Changes the trader a paired chat talks to.

        Args:
            chat_id (int): The chat.
            trader (str): The trader.

        Raises:
            PairingError: The chat is not paired.
        """
        with self._lock:
            data = self._read_live()
            for entry in data['paired']:
                if entry['chat_id'] == chat_id:
                    entry['trader'] = trader
                    self._write(data)
                    return
        raise PairingError(f'Chat {chat_id} is not paired')

    def _read_live(self) -> dict[str, list[dict[str, Any]]]:
        """Reads the file, leaving out expired codes.

        Returns:
            dict[str, list[dict[str, Any]]]: The "paired" and "pending" lists.
        """
        data = {
            'paired': [],
            'pending': [],
        }
        if self._path.is_file():
            try:
                stored = json.loads(self._path.read_text(encoding='utf-8'))
            except ValueError:
                _LOGGER.exception(
                    'The Telegram pairing file is damaged; treating it as empty'
                )
                stored = {}
            data['paired'] = list(stored.get('paired', []))
            data['pending'] = list(stored.get('pending', []))
        oldest = self._now() - _CODE_LIFETIME
        live = []
        for entry in data['pending']:
            if datetime.datetime.fromisoformat(entry['requested_at']) >= oldest:
                live.append(entry)
        data['pending'] = live
        return data

    def _write(self, data: dict[str, list[dict[str, Any]]]) -> None:
        """Writes the file in one step, so a crash never leaves half a file.

        Args:
            data (dict[str, list[dict[str, Any]]]): The lists.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(
            dir=self._path.parent, prefix='.telegram_pairing.'
        )
        with os.fdopen(handle, 'w', encoding='utf-8') as file:
            json.dump(data, file, indent=2)
        Path(temporary).replace(self._path)

    def _new_code(self) -> str:
        """Makes a random code from letters and digits that cannot be mistaken for each other.

        Returns:
            str: Eight characters, without 0, O, 1 or I.
        """
        characters = []
        for _ in range(_CODE_LENGTH):
            characters.append(secrets.choice(_CODE_ALPHABET))
        return ''.join(characters)

    def _now(self) -> datetime.datetime:
        """The current time.

        Returns:
            datetime.datetime: Now, in UTC.
        """
        if self._clock is not None:
            return self._clock()
        return datetime.datetime.now(datetime.UTC)
