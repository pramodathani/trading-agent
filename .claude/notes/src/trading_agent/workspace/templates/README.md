# workspace/templates

These Markdown files are the starting text of the workspace files and the first-run interview's instructions. They are content, not code, so their wording is what shapes the agent's behaviour.

- `Agents.md` tells every desk how to work: use tools for facts, never invent prices, never wait for permission, accept the risk engine's refusals as final, and never disconnect UBI.
- `TradingRules.md` starts with `trading_enabled = false` and zero limits in its fenced `toml limits` block, so that before the user fills it in the risk engine (milestone 9) refuses every order. Its limits are percentages of the total balance across all brokers, which the risk engine reads live from UBI, because that is how the user stated them on 2026-10-17. It has a weekly loss limit, and `maximum_open_positions` is optional, so leaving it out means no cap.
- `FirstRunInterview.md` is appended to the prompt while `User.md` is a template. It asks for one topic at a time and ends with one `propose_file_change` per file, so the user's files only change when the user accepts.

On 2026-10-17 the user chose a shared capital pool with no per-desk caps and no orders-per-minute cap, so `capital_share_percent` and `maximum_orders_per_minute` became optional per-desk keys, left out by default. The user's rule "options only long, no option writing without explicit permission" became the `allow_option_writing = false` switch, so the risk engine enforces it rather than relying on the model to remember it.

The user asked on 2026-10-17 for the trading window to be each exchange's own opening and closing times, so `trading_window = "exchange_hours"` became the default. A fixed India-time range is still accepted and applies to every exchange. The exchanges' hours come from the market calendar (milestone 15), because MCX's closing time moves with US daylight saving.
