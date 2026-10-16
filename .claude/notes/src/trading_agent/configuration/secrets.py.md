# secrets.py

Secrets are read with pydantic-settings, the same way sridhara reads `SRIDHARA_*` variables. The prefix `TRADING_AGENT_` keeps them apart from other projects' variables in the same shell.

`claude_code_oauth_token` is stored under our own prefix and passed to Claude Code as `CLAUDE_CODE_OAUTH_TOKEN` only in the environment of the process the Claude backend starts (milestone 3). Keeping it out of the gateway's own environment means the sandboxed bash terminal never inherits it.
