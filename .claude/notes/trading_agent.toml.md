# trading_agent.toml

Model order chosen by the user on 2026-10-18: main, intraday and positional use Claude Opus 5.5 at medium effort, then DeepSeek V4 Pro, then Qwen, then Gemma. The scalper, which wakes every 2 minutes, uses Claude Sonnet 5.5 at low effort first: its checks need speed more than deep reasoning, and Opus there would use up the shared Max limit and push every trader to DeepSeek. Sonnet's `context_window` is set to 200,000 as a cautious value; Claude Code compacts by the real window regardless, so a smaller value only makes the trader's own flush-and-compact happen earlier.

`[approvals] tools = ["flatten_trader"]` with a 5-minute expiry was chosen by the user the same day.
