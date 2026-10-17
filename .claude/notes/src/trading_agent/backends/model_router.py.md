# model_router.py

The router is the user's "switch down a chain" decision in code. Each desk has its own router over the backends in its `backend_order`.

## Waiting periods

A failed backend is not tried again until its waiting period ends: 30 s after the first failure in a row, 60 s after the second, 300 s after every later one, and back to 30 s after a success. These are the cooldowns OpenClaw documents for its model failover. Without them, every turn during a Claude outage would first spend time on a request that is bound to fail, and Claude Code would be restarted on every turn. The clock is passed in so the tests can move time forward instead of sleeping.

## Hand-over

Each backend keeps its own memory: the agent-loop backends each have their own `Conversation`, and Claude has its own Claude Code session. When a backend runs a turn after others have answered turns it never saw, the router puts those exchanges (trigger and final answer, the last 10 at most) in front of the trigger's text, marked as a hand-over. This is deliberately simple; milestone 11 replaces it with the desk's session-memory summary.

Only the trigger and the final answer are handed over, not the tool calls in between. If a backend fails part-way through a turn after it has already run tools, the next backend repeats the turn without knowing what was already done. That matters once order tools exist: the risk engine (milestone 9) and order tagging will have to make a repeated order harmless.

## Verified on 2026-10-16

With a deliberately wrong Claude token, the first turn published `backend_unavailable` for Claude (`authentication_failed`, waiting 30 s), Qwen answered the same turn with a `get_time` call in 12.5 s (most of it Ollama loading the model), and the second turn went straight to Qwen in 0.6 s without trying Claude.

## Sessions on disk (milestone 11)

With a `SessionStore`, `_finish` appends every exchange to the session log and rewrites `state.json` with each route's `exchanges_seen` and its runner's `saved_state()`. `restore_session` reads them back at start-up: a route whose runner's `restore_state` succeeds (Claude, when Claude Code still has the session file) keeps its `exchanges_seen`, capped at the number of exchanges actually in the log; every other route starts at 0, so its next turn begins with the normal hand-over. `reset` (for `/new` and the daily rollover) now also begins a new session in the store.

The hand-over paragraph above said milestone 11 would replace it with a session summary. It did not: the hand-over turned out to be exactly the right mechanism for crash recovery too, so it stays, and the daily summary covers the different job of carrying one day into the next.

`/model` preferences are not saved; after a restart the configured order applies again.

Verified on 2026-10-17: after a restart Claude resumed its saved session and recalled a codeword without any tool, and Qwen, asked first, received the session's exchanges as a hand-over and recalled it too.

## /compact (milestone 12)

`compact` asks the backend that answered last to compact its own conversation, because that is the conversation in use. A failure is reported as text, not raised, because `/compact` is a command and should always get an answer.
