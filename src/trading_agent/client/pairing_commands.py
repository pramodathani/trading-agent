"""The `trading-agent pairing` commands: list, approve and revoke Telegram chats.

They work on the pairing file directly, so they work whether or not the gateway is running, and the running gateway sees the change at the chat's next message.

Typical usage example:

  exit_code = PairingCommands(store, 'main').approve('ABCD2345')
"""

import sys
from typing import TextIO

from trading_agent.channels import pairing_store as pairing_store_module


class PairingCommands:
    """Manages Telegram pairings for the user."""

    def __init__(
        self,
        store: pairing_store_module.PairingStore,
        default_trader: str,
        output: TextIO = sys.stdout,
    ):
        """Creates the commands.

        Args:
            store (pairing_store_module.PairingStore): The pairing file.
            default_trader (str): The trader a newly paired chat talks to.
            output (TextIO): Where to print.
        """
        self._store = store
        self._default_trader = default_trader
        self._output = output

    def list(self) -> int:
        """Prints the paired chats and the codes waiting for approval.

        Returns:
            int: Always 0.
        """
        chats = self._store.paired_chats()
        if not chats:
            self._print('No chat is paired.')
        for chat in chats:
            self._print(
                f'paired: {chat.name or "(no name)"}, chat {chat.chat_id}, trader {chat.trader}, since {chat.paired_at}'
            )
        for pending in self._store.pending():
            self._print(
                f'waiting: code {pending.code} from {pending.name or "(no name)"}, chat {pending.chat_id}, asked at {pending.requested_at}'
            )
        return 0

    def approve(self, code: str) -> int:
        """Pairs the chat that was given a code.

        Args:
            code (str): The code the bot sent.

        Returns:
            int: 0 when paired, 1 when no valid code matches.
        """
        try:
            chat = self._store.approve(code, self._default_trader)
        except pairing_store_module.PairingError as error:
            self._print(str(error))
            return 1
        self._print(
            f'Paired {chat.name or "the chat"} (chat {chat.chat_id}); it talks to {chat.trader}. Send the bot any message to start.'
        )
        return 0

    def revoke(self, chat_id: str) -> int:
        """Unpairs a chat.

        Args:
            chat_id (str): The chat's id, as `pairing list` prints it.

        Returns:
            int: 0 when removed, 1 when the chat was not paired or the id is not a number.
        """
        try:
            chat = self._store.revoke(int(chat_id))
        except (ValueError, pairing_store_module.PairingError) as error:
            self._print(str(error))
            return 1
        self._print(
            f'Unpaired {chat.name or "the chat"} (chat {chat.chat_id}). The bot will ignore it.'
        )
        return 0

    def _print(self, line: str) -> None:
        """Prints one line.

        Args:
            line (str): The line.
        """
        print(line, file=self._output)
