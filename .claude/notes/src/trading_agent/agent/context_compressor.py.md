# context_compressor.py

Context compression is block 35 of the plan, for the agent-loop backends (Qwen and Gemma on Ollama, and OpenAI-compatible servers). Claude's side is in `claude_code_turn_runner.py`.

## Why it is needed

Qwen and Gemma are given 32,768 tokens. About 6,200 of those go on the instructions and tool descriptions before any conversation (measured on 2026-10-17), and one `get_candles` turn adds about 1,600. When a request exceeds `num_ctx`, Ollama does not fail: it silently drops the oldest tokens, which can include the system prompt and therefore the trading rules. The desk would carry on without knowing its limits. Compression stops the conversation getting there.

## Two thresholds

| When | Threshold | What happens |
|---|---|---|
| Before a turn | `compression_threshold`, 0.70 | Memory-flush turn, then the whole conversation is summarised |
| Between the tool rounds of one turn | `emergency_compression_threshold`, 0.85 | Everything before the current turn is summarised at once; the current turn's messages are kept |

The flush cannot happen mid-turn: the last message is a tool result waiting for the model, and inserting a user message there would break the turn's structure.

## The memory flush

A silent turn, run through the normal loop with tools, asking the desk to save what it will need with `add_note` and Memory.md, and not to trade. Its trigger has source `compression`. It is silent in that its reply is not shown to the user as an answer; its tool calls and model usage are still journaled. Its exchange is then summarised along with everything else.

## The summary

The same model writes the summary, with no tools offered, from a plain-text transcript, not from the raw messages. The transcript shortens long parts (tool results to 1,500 characters, tool arguments to 300) and fits in half the context window. It always keeps the first message, which after an earlier compression holds the previous summary, and drops the oldest of the rest when needed. The summariser is told what to keep (`SUMMARY_FOCUS`, shared with Claude's `/compact` instructions) and never to invent numbers.

## A bug found in the live test

The first version marked a shortened tool result with a bare "…". Qwen's summary then said the candle feed "was cut off mid-row on 9 Oct", and in the next turn Qwen refused to stand by a 30-day high it had reported correctly from the full data. The shortening now says `[… shortened for this summary; the desk saw the full text]`, and the summariser prompt says to trust the answers given at the time. The repeated test with INFY then recalled the high and low exactly.

## Afterwards

The conversation restarts with one user message holding the summary, marked as such and pointing to notes, Memory.md and `search_sessions` for the full record, followed by the kept messages. A `context_compressed` event records the backend, reason, tokens before, messages summarised and kept, and the summary's length.

If the summary call fails, the error goes up to the router, which tries the next backend as for any other failure.

## Verified on 2026-10-17

- `/compact` on Qwen: 6 messages (about 8,100 tokens) became a 1,726-character summary; the next prompt was 6,723 tokens, and Qwen recalled RELIANCE's 14 Oct close (₹1,174.6) from the summary alone.
- Automatic path, with the threshold lowered to 0.22 for the test only: at the second turn Qwen was at 8,684 tokens, the flush ran, 8 messages were summarised, and the turn ran on 6,980 tokens.

Pictures are never part of the summary request, because the transcript is plain text. Since attachments part 3 the transcript says where a message carried pictures ("Message to you [with 2 picture(s)]", "Tool view_image returned a picture and: …"), so the summary can mention that a picture was discussed and the desk knows to use `view_image` to see it again.
