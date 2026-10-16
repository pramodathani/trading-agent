# secrets.py

Secrets are read with pydantic-settings, the same way sridhara reads `SRIDHARA_*` variables. The prefix `TRADING_AGENT_` keeps them apart from other projects' variables in the same shell. A variable set in the environment wins over the same name in `.env`, which is how the fallback test on 2026-10-16 ran with a deliberately wrong Claude token without editing `.env`.

`claude_code_oauth_token` is stored under our own prefix and passed to Claude Code as `CLAUDE_CODE_OAUTH_TOKEN` only in the environment of the process the Claude backend starts.

`openai_api_key` is used by every `openai_compatible` backend; local servers that need no key leave it empty.
