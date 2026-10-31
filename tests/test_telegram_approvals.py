"""Tests for deciding held actions on Telegram by typing /approve or /deny."""

import asyncio
from pathlib import Path

from tests import test_permissions
from trading_agent.channels import pairing_store as pairing_store_module
from trading_agent.channels import telegram_commands
from trading_agent.requests import user_request as user_request_module

_OWNER = 111


class _Approvals:
    """A trader whose echo tool needs permission, and the Telegram commands that decide it.

    Attributes:
        permissions: The trader, its gate, store, grants and responder.
        commands: The Telegram commands.
        chat: The owner's paired chat.
    """

    def __init__(self, directory: Path):
        """Builds everything with the owner paired to the main trader.

        Args:
            directory (Path): A scratch folder.
        """
        self.permissions = test_permissions._Permissions(directory)
        pairing = pairing_store_module.PairingStore(
            directory / 'telegram_pairing.json'
        )
        pairing.approve(pairing.request(_OWNER, 'Owner'), 'main')
        self.chat = pairing.paired_chat(_OWNER)
        self.commands = telegram_commands.TelegramCommands(
            {},
            None,
            pairing,
            'dry_run',
            request_store=self.permissions.store,
            responder=self.permissions.responder,
        )

    def say(self, text: str) -> str:
        """Sends one command and returns the reply.

        Args:
            text (str): The command.

        Returns:
            str: The reply.
        """
        assert self.commands.handles(text)
        return asyncio.run(self.commands.answer(self.chat, text))

    def short_id(self, index: int) -> str:
        """The last six characters of a waiting request's id, as the user would type them.

        Args:
            index (int): Which waiting request, oldest first.

        Returns:
            str: The short id.
        """
        request_id = self.permissions.store.pending()[index].request_id
        return request_id.rsplit('-', 1)[-1]


class TestTelegramApprovals:
    """Tests for /approve and /deny."""

    def test_approve_the_only_waiting_action(self, tmp_path: Path) -> None:
        """With one action waiting, /approve needs no id, runs the action once, and tells the trader."""
        approvals = _Approvals(tmp_path)
        approvals.permissions.call()

        reply = approvals.say('/approve')

        request = approvals.permissions.store.all()[0]
        assert reply.startswith('Allowed echo for the main trader, this once.')
        assert request.status == user_request_module.ANSWERED
        assert request.responded_via == 'telegram'
        assert len(approvals.permissions.trader.triggers) == 1
        assert not approvals.permissions.grants.allows('main', 'echo')

    def test_approve_always_by_short_id(self, tmp_path: Path) -> None:
        """/approve <short id> always allows the action and saves a standing permission."""
        approvals = _Approvals(tmp_path)
        approvals.permissions.call()

        reply = approvals.say(f'/approve {approvals.short_id(0)} always')

        assert 'from now on' in reply
        assert approvals.permissions.grants.allows('main', 'echo')

    def test_deny_with_a_reason(self, tmp_path: Path) -> None:
        """/deny with words but no id refuses the only waiting action, keeping the words as the reason."""
        approvals = _Approvals(tmp_path)
        approvals.permissions.call()

        reply = approvals.say('/deny too risky today')

        request = approvals.permissions.store.all()[0]
        assert reply.startswith('Denied echo for the main trader.')
        assert request.response['reason'] == 'too risky today'

    def test_several_waiting_actions_need_an_id(self, tmp_path: Path) -> None:
        """With two actions waiting, /approve lists them, and /approve <short id> decides only that one."""
        approvals = _Approvals(tmp_path)
        approvals.permissions.call('first')
        approvals.permissions.call('second')
        second = approvals.short_id(1)

        listing = approvals.say('/approve')
        reply = approvals.say(f'/approve {second}')

        assert listing.startswith('Several actions are waiting.')
        assert f'{second} - main: echo' in listing
        assert reply.startswith('Allowed echo')
        assert len(approvals.permissions.store.pending()) == 1

    def test_nothing_waiting(self, tmp_path: Path) -> None:
        """/deny with nothing waiting says so."""
        approvals = _Approvals(tmp_path)

        assert (
            approvals.say('/deny')
            == 'No action is waiting for your permission.'
        )
