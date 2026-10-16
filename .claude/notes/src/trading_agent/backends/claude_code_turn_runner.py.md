# claude_code_turn_runner.py

Claude Code runs its own agent loop, so Claude is a turn runner rather than a `ModelBackend`. It keeps one `ClaudeSDKClient`, and therefore one Claude Code process and session, per desk; Claude remembers earlier turns because the session continues. After a failure the client is dropped and the next turn starts a new process with `resume=<session_id>`, so the memory survives a crash of Claude Code.

## Changed workspace files reach Claude inside the message

A resumed Claude Code session keeps the system prompt it started with and ignores the one passed when it is resumed. This was found on 2026-10-17 with Claude Code 2.1.301: after `TradingRules.md` changed, the restarted process's command line held the new prompt (`capital_percent` present, the old rupee keys absent), yet the model quoted the old keys word for word. The milestone 5 design of restarting Claude Code with the new prompt was therefore removed.

Instead, when the prompt's fingerprint differs from the one the session last saw, the next message starts with a marked block holding the complete current prompt, which the model is told replaces the earlier versions. Because the block is part of the conversation, it survives a later crash and resume. The cost is the prompt's length once per change, which Claude Code's own compaction absorbs over time.

## Never stopping for a human

- `permission_mode='bypassPermissions'` with `setting_sources=[]`: no settings file is read, so there are no "ask" rules, and the user's global `~/.claude/CLAUDE.md` is not loaded either (the probe confirmed Claude saw no mention of the Google style guide).
- `CLAUDE_CODE_OAUTH_TOKEN` comes from `claude setup-token`; there is no login prompt.

## Subscription, not API

The SDK copies the whole parent environment into Claude Code and `options.env` can only add or replace variables, not remove them (`subprocess_cli.py`, version 0.2.168). An `ANTHROPIC_API_KEY` in the gateway's environment would therefore reach Claude Code and be billed. The runner refuses to start while that variable exists, which is a stronger guarantee than trying to blank it. The probe and the live run reported `apiKeySource: none` and a `five_hour` rate-limit window, both of which only appear on the subscription.

`total_cost_usd` is what the turn would cost on the API. Claude Code reports it even on a subscription, so it is published as `api_equivalent_cost_usd` and never treated as money spent.

## Limits

A `RateLimitEvent` with status `rejected` (the 5-hour or weekly limit) raises `BackendUnavailableError`, as does an assistant message with an `error` or a result marked `is_error`. The model router (milestone 4) catches it and moves to the next backend.

## Shutdown

`close` disconnects the client. The first live run showed Claude Code outliving the gateway briefly after shutdown, so the desk now closes its runner when it stops; afterwards the process count went from 1 while serving to 0 after shutdown.

## Measured on 2026-10-16

Three turns through the gateway took 3.4 s (with a `get_time` call), 2.0 s and 1.2 s. About 1,100 to 1,300 prompt tokens per turn were read from Anthropic's prompt cache, with only 2 to 4 new ones, because the system prompt and history stay the same between turns.

Verified live on 2026-10-17: after `TradingRules.md` changed mid-interview, the next reply began "Yes, I received updated instructions in this message" and quoted the new `allow_option_writing` key, without a restart.

## tradingmachine's settings are blanked

From milestone 8 the gateway loads tradingmachine's `.env`, which copies its settings, including database passwords, into the gateway's environment, and the SDK copies that whole environment into Claude Code. `_environment` therefore passes every `TRADINGMACHINE_` variable as an empty value. Claude Code has no tool that could read its environment, so this is defence in depth. Verified on 2026-10-17 by reading `/proc/<pid>/environ` of a Claude Code process started after the settings were loaded: all 16 were empty.
