# session_store.py

The session store is what lets a trader survive a restart (milestone 11, block 32). Before it, a gateway restart made every backend forget the conversation, including Claude, whose session id lived only in memory.

## What is kept, and where

Everything lives in `workspace/traders/<trader>/sessions/`, which is code-owned: the trader's file tools cannot write there (`path_policy.py` allows only `Memory.md`, `memory/`, `notes/` and `scratch/`), and the checkpoints do not track it, so restoring a checkpoint never rolls back the session record.

| File | Written by | Read by |
|---|---|---|
| `state.json` | the router after every finished turn and at every new session | the router at start-up |
| `<session_id>.jsonl` | the router, one exchange per line | the router at start-up, for hand-overs |
| `summaries/<date>.md` | the session keeper at rollover | the session keeper, to seed the next session; `session_search.py` |

## Decisions

- A session id is `<India date>-<n>`. `new_session_id` creates the empty log file at once, so the numbering stays unique even for a session that never finishes a turn, such as one started by `/new` and immediately replaced.
- `state.json` is written to a temporary file and renamed over the old one. A rename is atomic on Linux, so a crash mid-write leaves the previous state, never half a file.
- A damaged state file is treated as missing and logged. The trader then starts a new session instead of refusing to start, because a trader that does not start cannot trade or be flattened.
- A damaged log line (typically the last one, cut short by a crash) is skipped rather than failing the whole read.
- `Exchange` moved here from `model_router.py`, so the memory package does not import the backends package. It gained `finished_at`, used by search snippets and by anyone reading the logs.
- "Today" is the India date, through an injectable date source, so tests can move from Monday to Tuesday without waiting.

## Why the agent-loop conversations are not saved

The local and OpenAI backends keep their full conversation, tool calls and screenshots included, only in memory. Saving and replaying it would mean serialising images and every tool result, and the replayed history would immediately blow past Gemma's 32,000-token window. Instead, after a restart those backends start empty and the router's existing hand-over gives them the session's last 10 exchanges. Claude is different because Claude Code already persists its own session on disk, so only its id needs saving.

## Listing sessions (milestone 17)

`session_ids` and `summaries` list what is on disk for the Sessions page, newest first.
