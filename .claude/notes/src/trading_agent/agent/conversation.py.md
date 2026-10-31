# conversation.py

The conversation is append-only on purpose. Claude Opus 5.5 checks that the history sent with each request was not edited after its thinking was produced ("preserved thinking"), and accounts created after 2026-08-31 get an error when it was. Compression in milestone 12 therefore starts a fresh conversation seeded with a summary rather than editing this one.

## Size and restart (milestone 12)

The conversation lives only in memory; after a restart the router's hand-over fills it in (milestone 11). It no longer grows without limit.

`record_usage` stores the prompt plus reply tokens the server reported at the last call, and which messages that count covered. `estimated_tokens` adds about one token per three characters for messages appended since, which are mostly tool results. The estimate matters because the count is always one call behind: after a tool round, the next prompt includes the tool results the server has not counted yet. Three characters per token overestimates for English text (closer to four), which errs towards compressing a little early.

`restart` replaces the whole list in one step. It is the "fresh conversation seeded with a summary" described above, done in place so the agent turn runner and the loop keep the same object even when compression happens in the middle of a turn. No single message is ever edited. Preserved thinking does not apply here anyway, because Claude runs through its own Claude Code session and never through this class.

Verified on 2026-10-17: Ollama's `prompt_eval_count` reports the whole prompt even when it reuses its cache (13,916 tokens, then 13,933 on a follow-up with the same prefix), so the server's count can be trusted.

## Pictures in the estimate, since 2026-10-17

`estimated_tokens` adds 1500 tokens for each picture added since the last measurement, on user messages and tool results alike. Gemma counts a picture as up to about 1120 tokens and Claude up to about 1600 at the size pictures are sent; 1500 errs towards compressing a little early rather than overflowing a local model's 32,768-token window. Once the model has answered, its reported token count replaces the estimate.

Compression keeps no pictures: the summary is written from the messages' text, and the attachment notes in that text keep the files' paths, so the trader can still find an upload afterwards.

## Taking older pictures out

`keep_newest_pictures` breaks the old rule that messages are never edited one by one, and it is the only method that does. The reason is cost: Ollama and Chat Completions servers are sent the whole conversation with every call, so a picture left in the history is paid for again, at about 1,500 tokens, on every later call. A scalper taking a screenshot every few minutes would otherwise fill Gemma's 32,768-token window with pictures in under twenty calls.

A removed picture is replaced by a note in the message's text, not dropped silently, so the model knows something was there. The tool results of `browser_screenshot` and `view_image`, and the attachment line of a user message, already name the saved file, which is why the note points at "a saved path given above" and `view_image`. An MCP tool's picture has no saved path and cannot be brought back.

A message is kept whole or emptied whole: a user message with three pictures is not split, so slightly more than `count` pictures can remain. Counting from the newest backwards keeps the pictures of the current turn, which are the ones the model is working with.

Editing an older message changes the conversation's prefix, which ends the model server's prompt cache from that message on. That happens only when a fifth picture arrives, and resending a cached prefix is still cheaper than carrying every picture.

`measured_tokens` is not lowered when pictures are removed. The next call measures the real number, and until then the estimate errs high, which can only make compression come a little early.

## copy, since 2026-10-18

`copy` exists for `/btw`: a side question is asked on a copy so the real conversation never sees it. The copy shares the message objects, which is safe because messages are never changed after they are appended.
