# secrets.py

Secrets are read with pydantic-settings, the same way sridhara reads `SRIDHARA_*` variables. The prefix `TRADING_AGENT_` keeps them apart from other projects' variables in the same shell. A variable set in the environment wins over the same name in `.env`, which is how the fallback test on 2026-10-16 ran with a deliberately wrong Claude token without editing `.env`.

`claude_code_oauth_token` is stored under our own prefix and passed to Claude Code as `CLAUDE_CODE_OAUTH_TOKEN` only in the environment of the process the Claude backend starts.

`openai_api_key` is used by every `openai_compatible` backend; local servers that need no key leave it empty.

## webhook_token (milestone 15)

`TRADING_AGENT_WEBHOOK_TOKEN` in .env, for incoming webhooks; empty switches them off.

`telegram_bot_token` (milestone 19) comes from TRADING_AGENT_TELEGRAM_BOT_TOKEN. Like every secret, an environment variable of the same name takes precedence over .env.

## typesafe_api_key

The Jev key is read as `TRADING_AGENT_TYPESAFE_API_KEY`, through the class's prefix like the other secrets, rather than TypeSafe's own `TYPESAFE_API_KEY`. The bash sandbox replaces `.env` with an empty file and starts with an empty environment, so traders cannot read it.
