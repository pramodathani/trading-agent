"""Checks that a phone is paired, so alerts can reach the user away from the computer.

Typical usage example:

  result = TelegramPairingCheck(enabled, store).run()
"""

from trading_agent.channels import pairing_store as pairing_store_module
from trading_agent.doctor import doctor_check


class TelegramPairingCheck(doctor_check.DoctorCheck):
    """Counts the paired Telegram chats."""

    name = 'Telegram pairing'

    def __init__(self, enabled: bool, store: pairing_store_module.PairingStore):
        """Creates the check.

        Args:
            enabled (bool): Whether [telegram] is enabled.
            store (pairing_store_module.PairingStore): The pairing file.
        """
        self._enabled = enabled
        self._store = store

    def run(self) -> doctor_check.CheckResult:
        """Counts paired chats.

        Returns:
            doctor_check.CheckResult: OK when Telegram is on with a paired chat; a warning otherwise, since going live without it is allowed but alerts then reach only the web page.
        """
        chats = self._store.paired_chats()
        if self._enabled and chats:
            names = ', '.join(chat.name or str(chat.chat_id) for chat in chats)
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.OK, f'Alerts go to {names}.'
            )
        return doctor_check.CheckResult(
            doctor_check.CheckStatus.WARNING,
            'No phone is paired, so fills, halts and the kill switch are seen only on the web page. See docs/telegram_setup.md.',
        )
