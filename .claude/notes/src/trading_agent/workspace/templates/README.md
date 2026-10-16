# workspace/templates

These Markdown files are the starting text of the workspace files and the first-run interview's instructions. They are content, not code, so their wording is what shapes the agent's behaviour.

- `Agents.md` tells every desk how to work: use tools for facts, never invent prices, never wait for permission, accept the risk engine's refusals as final, and never disconnect UBI.
- `TradingRules.md` starts with `trading_enabled = false` and zero limits in its fenced `toml limits` block, so that before the user fills it in the risk engine (milestone 9) refuses every order. Its limits are percentages of the total balance across all brokers, which the risk engine reads live from UBI, because that is how the user stated them on 2026-10-17. It has a weekly loss limit, and `maximum_open_positions` is optional, so leaving it out means no cap.
- `FirstRunInterview.md` is appended to the prompt while `User.md` is a template. It asks for one topic at a time and ends with one `propose_file_change` per file, so the user's files only change when the user accepts.
