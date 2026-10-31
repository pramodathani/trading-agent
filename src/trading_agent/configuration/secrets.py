"""Secrets read from TRADING_AGENT_* environment variables and the .env file.

Secrets are kept apart from trading_agent.toml so that the TOML file can be committed to git while .env never is. `bin/trading-agent` changes into the project folder first, so `.env` is found there.

Typical usage example:

  secrets = Secrets()
  token = secrets.gateway_access_token
"""

import os
from pathlib import Path

import dotenv
import pydantic_settings


class Secrets(pydantic_settings.BaseSettings):
    """The secret values the agent needs.

    Attributes:
        gateway_access_token: The token every web interface and API request must present.
        claude_code_oauth_token: The Max subscription token made by `claude setup-token`, passed to Claude Code as CLAUDE_CODE_OAUTH_TOKEN.
        openai_api_key: The key for OpenAI-compatible backends, or empty for local servers that need none.
        webhook_token: The token incoming webhooks must present, kept apart from the gateway token so it can be pasted into services such as TradingView; empty switches webhooks off.
        telegram_bot_token: The token BotFather gave for the trading-agent bot, or empty when Telegram is not set up.
        firebase_service_account_file: The path of the Firebase service-account key JSON that lets the gateway send push notifications, or empty when push is not set up.
        typesafe_api_key: The TypeSafe AI key for the Jev decision model, or empty when no trader uses Jev.
    """

    model_config = pydantic_settings.SettingsConfigDict(
        env_prefix='TRADING_AGENT_',
        env_file='.env',
        extra='ignore',
    )

    gateway_access_token: str = ''
    claude_code_oauth_token: str = ''
    openai_api_key: str = ''
    webhook_token: str = ''
    telegram_bot_token: str = ''
    firebase_service_account_file: str = ''
    typesafe_api_key: str = ''

    def named(self, variable: str) -> str:
        """Reads a secret by its own name, such as DEEPSEEK_API_KEY, from the environment or the .env file.

        It serves backends whose key is named in trading_agent.toml with api_key_variable.

        Args:
            variable (str): The variable's full name.

        Returns:
            str: The value, or an empty string when it is not set.
        """
        value = os.environ.get(variable)
        if value:
            return value
        env_file = Path('.env')
        if not env_file.is_file():
            return ''
        return dotenv.dotenv_values(env_file).get(variable) or ''
