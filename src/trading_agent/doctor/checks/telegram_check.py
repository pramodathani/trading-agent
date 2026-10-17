"""Checks the Telegram bot token, by asking Telegram who the bot is.

Telegram's addresses contain the bot token, and httpx puts the address in its error messages, so this check reports only the kind of error, never its text.

Typical usage example:

  result = TelegramCheck(configuration.telegram, secrets).run()
"""

import httpx

from trading_agent.configuration import agent_configuration
from trading_agent.configuration import secrets as secrets_module
from trading_agent.doctor import doctor_check

_TIMEOUT_SECONDS = 15.0
_GUIDE = 'docs/telegram_setup.md'
_UNAUTHORISED = 401


class TelegramCheck(doctor_check.DoctorCheck):
    """Checks that Telegram is either off, or on with a token Telegram accepts."""

    name = 'Telegram'

    def __init__(
        self,
        configuration: agent_configuration.TelegramConfiguration,
        secrets: secrets_module.Secrets,
    ):
        """Creates the check.

        Args:
            configuration (agent_configuration.TelegramConfiguration): The [telegram] settings.
            secrets (secrets_module.Secrets): The secrets, holding the bot token.
        """
        self._configuration = configuration
        self._token = secrets.telegram_bot_token

    def run(self) -> doctor_check.CheckResult:
        """Asks Telegram for the bot's name when a token is set.

        Returns:
            doctor_check.CheckResult: OK when Telegram is off without a token or the token works; a warning when a working token is set but Telegram is off; failed when it is on without a token or Telegram refuses the token.
        """
        if not self._token:
            if self._configuration.enabled:
                return doctor_check.CheckResult(
                    doctor_check.CheckStatus.FAILED,
                    f'[telegram] is enabled but TRADING_AGENT_TELEGRAM_BOT_TOKEN is not set in .env; follow {_GUIDE}.',
                )
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.OK,
                f'Telegram is switched off. To set it up, follow {_GUIDE}.',
            )
        try:
            response = httpx.get(
                f'https://api.telegram.org/bot{self._token}/getMe',
                timeout=_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as error:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.FAILED,
                f'Telegram could not be reached ({type(error).__name__}); check the internet connection.',
            )
        if response.status_code == _UNAUTHORISED:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.FAILED,
                'Telegram refused the bot token. Copy it again from BotFather into TRADING_AGENT_TELEGRAM_BOT_TOKEN in .env.',
            )
        if not response.is_success:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.FAILED,
                f'Telegram answered with status {response.status_code}.',
            )
        username = response.json().get('result', {}).get('username', '')
        if not self._configuration.enabled:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.WARNING,
                f'The token works (bot @{username}), but [telegram] enabled is false in trading_agent.toml.',
            )
        return doctor_check.CheckResult(
            doctor_check.CheckStatus.OK,
            f'Telegram knows the bot as @{username}; chats must be paired before it obeys them.',
        )
