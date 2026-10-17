# agent_configuration.py

Every model uses `extra='forbid'`, so a misspelt key such as `modde` is reported rather than silently ignored. A trading agent whose `mode` setting was mistyped and quietly fell back to a default would be dangerous in either direction.

Desk names are limited to lower-case letters, digits and underscores, because a desk name becomes a folder name, an order tag sent to UBI and part of web addresses.

The `base_url` rule is a validator rather than a separate model per backend kind, because only that one field differs between kinds today. If the kinds grow apart, each can become its own model.

## Compression settings (milestone 12)

`[agent] compression_threshold` (0.70) and `emergency_compression_threshold` (0.85), with a check that the emergency one is higher. They apply to every backend: the local backends through `ContextCompressor`, Claude through the runner's own check and Claude Code's compaction window.

## Skills settings (milestone 13)

`[skills] archive_after_days` (30) and `[sandbox] passed_environment` (empty).

## mcp_servers_file (milestone 13)

Defaults to `mcp_servers.json` beside trading_agent.toml.

## Scheduling settings (milestone 15)

`market_calendar_directory` (UBI's calendars folder), and per desk `heartbeat_minutes` (off by default) and `rollover_time` (15:45).

## Backend prices (milestone 15)

`rupees_per_million_prompt_tokens` and `rupees_per_million_completion_tokens` on a backend let /usage show its cost.

## scheduled_checks (milestone 16)

A desk's list of HH:MM times for its routine checks.

## gateway.frontend_directory (milestone 18)

The built web page's folder, `frontend/dist` by default. It is relative to the project folder, because `bin/trading-agent` changes to the project folder before starting.

## [telegram] (milestone 19)

Off by default, because it needs a bot token the user creates. `notifications` is checked against the known names when the file is read, so a typing mistake is reported at start instead of silently pushing nothing. `default_desk` must be one of the desks.
