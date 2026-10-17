"""Secrets read from TRADING_AGENT_* environment variables and the .env file.

Secrets are kept apart from trading_agent.toml so that the TOML file can be committed to git while .env never is. `bin/trading-agent` changes into the project folder first, so `.env` is found there.

Typical usage example:

  secrets = Secrets()
  token = secrets.gateway_access_token
"""

import pydantic_settings


class Secrets(pydantic_settings.BaseSettings):
    """The secret values the agent needs.

    Attributes:
        gateway_access_token: The token every web interface and API request must present.
        claude_code_oauth_token: The Max subscription token made by `claude setup-token`, passed to Claude Code as CLAUDE_CODE_OAUTH_TOKEN.
        openai_api_key: The key for OpenAI-compatible backends, or empty for local servers that need none.
        webhook_token: The token incoming webhooks must present, kept apart from the gateway token so it can be pasted into services such as TradingView; empty switches webhooks off.
        telegram_bot_token: The token BotFather gave for the trading-agent bot, or empty when Telegram is not set up.
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
