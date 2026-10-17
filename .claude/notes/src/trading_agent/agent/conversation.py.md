# conversation.py

The conversation is append-only on purpose. Claude Opus 5.5 checks that the history sent with each request was not edited after its thinking was produced ("preserved thinking"), and accounts created after 2026-08-31 get an error when it was. Compression in milestone 12 therefore starts a fresh conversation seeded with a summary rather than editing this one.

## Size and restart (milestone 12)

The conversation lives only in memory; after a restart the router's hand-over fills it in (milestone 11). It no longer grows without limit.

`record_usage` stores the prompt plus reply tokens the server reported at the last call, and which messages that count covered. `estimated_tokens` adds about one token per three characters for messages appended since, which are mostly tool results. The estimate matters because the count is always one call behind: after a tool round, the next prompt includes the tool results the server has not counted yet. Three characters per token overestimates for English text (closer to four), which errs towards compressing a little early.

`restart` replaces the whole list in one step. It is the "fresh conversation seeded with a summary" described above, done in place so the agent turn runner and the loop keep the same object even when compression happens in the middle of a turn. No single message is ever edited. Preserved thinking does not apply here anyway, because Claude runs through its own Claude Code session and never through this class.

Verified on 2026-10-17: Ollama's `prompt_eval_count` reports the whole prompt even when it reuses its cache (13,916 tokens, then 13,933 on a follow-up with the same prefix), so the server's count can be trusted.
