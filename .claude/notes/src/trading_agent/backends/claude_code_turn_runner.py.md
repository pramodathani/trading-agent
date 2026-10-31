# claude_code_turn_runner.py

Claude Code runs its own agent loop, so Claude is a turn runner rather than a `ModelBackend`. It keeps one `ClaudeSDKClient`, and therefore one Claude Code process and session, per trader; Claude remembers earlier turns because the session continues. After a failure the client is dropped and the next turn starts a new process with `resume=<session_id>`, so the memory survives a crash of Claude Code.

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

`close` disconnects the client. The first live run showed Claude Code outliving the gateway briefly after shutdown, so the trader now closes its runner when it stops; afterwards the process count went from 1 while serving to 0 after shutdown.

## Measured on 2026-10-16

Three turns through the gateway took 3.4 s (with a `get_time` call), 2.0 s and 1.2 s. About 1,100 to 1,300 prompt tokens per turn were read from Anthropic's prompt cache, with only 2 to 4 new ones, because the system prompt and history stay the same between turns.

Verified live on 2026-10-17: after `TradingRules.md` changed mid-interview, the next reply began "Yes, I received updated instructions in this message" and quoted the new `allow_option_writing` key, without a restart.

## tradingmachine's settings are blanked

From milestone 8 the gateway loads tradingmachine's `.env`, which copies its settings, including database passwords, into the gateway's environment, and the SDK copies that whole environment into Claude Code. `_environment` therefore passes every `TRADINGMACHINE_` variable as an empty value. Claude Code has no tool that could read its environment, so this is defence in depth. Verified on 2026-10-17 by reading `/proc/<pid>/environ` of a Claude Code process started after the settings were loaded: all 16 were empty.

## Resuming after a restart (milestone 11)

`saved_state` returns the Claude Code session id and the fingerprint of the prompt that session last saw. `restore_state` sets them back so the next connect passes `resume=`; with the fingerprint restored, `_query_text` still delivers changed instruction files inside the next message.

Before resuming, the runner checks that Claude Code still has the session's file (`<sessions_directory>/*/<session_id>.jsonl`; the folder name encodes the working directory, so every folder is searched). Without that check, a deleted session would make every Claude turn fail with "no conversation found", the router would put Claude into its waiting periods, and Claude would never recover because the bad id would be retried each time. With the check, a missing session simply means a new one, and the router's hand-over fills it in.

`sessions_directory` is `$CLAUDE_CONFIG_DIR/projects`, or `~/.claude/projects` when that variable is not set (`trader_builder.py`).

## Compaction (milestone 12)

Measured on 2026-10-17 with `ClaudeSDKClient.get_context_usage()`, which asks Claude Code without calling the model:

| Setting | Threshold reported for opus (1,000,000 tokens) |
|---|---|
| Default | 967,000 (the window minus a 33,000 buffer) |
| `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=70` or `50` | 967,000, so no visible effect |
| `CLAUDE_CODE_AUTO_COMPACT_WINDOW=700000` | 667,000 |

The plan's `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` is in the binary and described as lowering the threshold, but the reported threshold ignored it, so it is not relied on. Instead:

- Before each turn on an existing session, the runner reads the session's `totalTokens`. At `compression_threshold` (0.70) of the window it runs a memory-flush turn (the same `FLUSH_REQUEST` as the local backends) and then sends `/compact Keep <SUMMARY_FOCUS>.` as a query. Claude Code treats a query starting with a slash as its own command, as the session file confirmed.
- `CLAUDE_CODE_AUTO_COMPACT_WINDOW` is set to `emergency_compression_threshold` times the window (850,000), so Claude Code's own compaction fires at 817,000 tokens, the safety net for one turn that grows past 70% by itself.
- After any compaction `note_compaction` clears the prompt fingerprint, so the instruction files are sent again. The heading of that message was reworded, because "have changed" was untrue after a compaction.

On a 1,000,000-token window, 70% is 700,000 tokens per request. In practice Claude reaches the daily rollover long before that, so this mostly matters for a very busy day; compacting earlier also uses less of the Max subscription's limits per turn.

Verified on 2026-10-17: `/compact` ran a flush turn (Claude saved a preference to Memory.md), then Claude Code compacted and recalled the preference afterwards. The size went from 16,792 to 16,885 tokens, because about 15,000 of a small session are the fixed instructions and tool descriptions, which compaction cannot remove.

## MCP_TOOL_TIMEOUT (milestone 14)

Claude Code limits how long one MCP tool call may take, and its default is not documented in the binary. delegate_task can wait up to 30 minutes for subagents, so the runner sets `MCP_TOOL_TIMEOUT` to 2,000,000 ms. trading-agent's own registry still applies each tool's shorter limit.

## Steering and /stop (milestone 18)

The PostToolUse hook list holds the steering hook when the trader has an inbox. A cancelled turn disconnects Claude Code, which stops its process; the next turn starts a new process and resumes the saved session, as after any failure.

## Pictures, since 2026-10-17

`client.query` takes either a string or an async iterable of messages. A turn with pictures is sent as one user message whose `content` is a text block followed by `image` blocks with base64 data, in the Messages API's format, which Claude Code passes on through its stream-json input. A turn without pictures still sends the plain string, so nothing changed for ordinary turns.

`_one_message` is an async generator because `query` iterates its argument with `async for`. It yields no `session_id`; `query` fills it in.

Checked on 2026-10-17: the main trader (opus) described a test picture exactly, and a picture dropped on the chat page ("9035" on green) came back correctly.

## /think, since 2026-10-18

Claude Code reads `effort` and `thinking` only when its process starts; the SDK has `set_model` for a running client but nothing for effort. So `set_thinking` only records the wish, and `_connected_client` compares the wanted pair (effort, thinking off) with the pair the running client was started with. When they differ, it disconnects and connects again. The new process resumes the same session (`resume=self.session_id`), so the conversation is kept, at the cost of one process restart (a few seconds) on the next turn.

`_applied_thinking` starts as the configured pair, so a client set up any other way, such as in tests, is not restarted for no reason.

`/think off` sends `thinking={'type': 'disabled'}` and keeps the effort as it was, so `/think high` after `/think off` turns thinking back on at high.

## Side questions, since 2026-10-18

The trader's long-lived Claude Code client would add a side question to the session, so `side_question` uses the SDK's standalone `query()` instead, with `resume=<session id>` and `fork_session=True`. Claude Code then copies the session into a new one, answers there, and leaves the trader's session file untouched. This runs in a second, short-lived Claude Code process, so it can run while the trader's own turn is in progress.

The fork keeps the trader's MCP server, because Claude's API refuses a conversation that holds tool calls when no tools are defined. Every call is refused instead, by `ClaudeToolAllowlistHook` with an empty allowlist, and the prompt asks for no tools. `max_turns` is 3, so a model that tries a tool anyway still has room to answer after the refusal.

The fork's session file is deleted afterwards (`_delete_fork`), so session search and `/resume` never find it. A fork id equal to the trader's session id is never deleted, as a guard.

The fork's cost is not recorded by the usage tracker; it counts against the Max subscription like any Claude Code call.
