# claude_pre_compact_hook.py

Claude Code calls PreCompact hooks before it compacts a session, whether automatically or because of `/compact`. The hook does two things:

1. It calls the runner's `note_compaction`, so the next turn's message carries the full instruction files again. Updated instructions delivered inside earlier messages (see `_query_text`) may not survive Claude Code's summary.
2. For an automatic compaction only, it publishes `context_compressed` with reason `claude_code_auto`. A manual one is always the runner's own `/compact`, which publishes a fuller event with tokens before and after, so publishing here too would record it twice.

The hook returns an empty dict, so compaction always goes ahead. It cannot run a memory flush itself: the hook runs inside Claude Code's compaction, not as a turn. That is why the runner does its own flush and `/compact` at 70%, and the automatic compaction is only the safety net.

Verified on 2026-10-17: Claude Code's session file recorded `Compacted PreCompact [callback] completed successfully` after the runner's `/compact`.
