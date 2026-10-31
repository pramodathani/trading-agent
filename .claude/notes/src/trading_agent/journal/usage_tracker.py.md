# usage_tracker.py

The usage tracker (block 41), behind `/usage`.

## Counting

From `model_usage` events: per India day, trader and backend, the calls (agent-loop rounds, or Claude turns), prompt and completion tokens, Claude's cache-read tokens and Claude's `api_equivalent_cost_usd` (what the turn would have cost on the API; nothing is charged per token on the subscription). From `rate_limit` events: each backend's latest status, utilisation and reset time.

For Claude, "tokens in" are only the uncached input tokens; most of a Claude session's input is read from the prompt cache and is shown separately.

## Rupees

An OpenAI-compatible backend can have `rupees_per_million_prompt_tokens` and `rupees_per_million_completion_tokens` in trading_agent.toml; without both, no cost is shown. No prices are guessed, because they change.

## Restart

`replay_today` re-reads today's journal lines from before the tracker started, then counts live events, so the day's totals survive a restart without double counting.

## Verified on 2026-10-17

/usage showed the whole day read back from the journal: Claude 19 turns, 594,578 cache-read tokens, an API-equivalent $2.67; Qwen 54 calls with 397,175 prompt tokens; Gemma 3 calls; and Claude's five-hour limit "allowed", resetting at 15:20.

## Rate limits for the API (milestone 17)

`rate_limits` returns copies of the latest reports so the API cannot change the tracker's own dictionaries.
