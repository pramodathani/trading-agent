# deepseek_backend.py

Built on 2026-10-18 for the user's plan: Claude first; DeepSeek V4 Pro when Claude's Max limit refuses; Qwen and Gemma only when both are out.

Facts checked against DeepSeek's documentation on 2026-10-18 (api-docs.deepseek.com, guides/thinking_mode and quick_start/error_codes):

- Thinking is on by default and arrives as `reasoning_content`. With tools in the request, "the reasoning_content must be fully passed back to the API in all subsequent requests", across user turns too, or the API returns 400. That is why `ConversationMessage` gained a `reasoning` field and the backend sends it back with every assistant message.
- `temperature`, `presence_penalty` and `frequency_penalty` have no effect in thinking mode.
- 402 is "Insufficient Balance". No balance endpoint is documented, so the backend waits 15 minutes after a 402 and tries again; a refused request costs nothing.

Prices in trading_agent.toml are the user's price list for deepseek-v4-pro at peak: $0.044 per million cached prompt tokens, $1.32 uncached, $3.96 output; off-peak is half, and peak is 01:00–04:00 and 06:00–10:00 UTC on weekdays (06:30–09:30 and 11:30–15:30 India time). Chinese public holidays, which DeepSeek treats as off-peak, are not known here, so those days are costed at peak.

V4 Pro cannot read pictures, so `vision = false` replaces pictures with a note. The user chose the full 1M window, knowing that a near-full uncached call costs about $0.92 at peak.
