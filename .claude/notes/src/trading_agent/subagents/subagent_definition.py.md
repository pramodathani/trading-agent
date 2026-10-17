# subagent_definition.py

Subagents (block 26) are defined in Claude Code's subagent format: a Markdown file with frontmatter `name`, `description`, `tools` and `model`, and the instructions as the body, so definitions can move between Claude Code and trading-agent.

## Fields and decisions

- `tools`: a comma-separated string (Claude Code's style) or a YAML list. Absent means the safe default set (see `subagent_toolbox.py`), not "every tool" as in Claude Code, because the plan says subagents get no order tools by default.
- `model`: a backend name from trading_agent.toml, a list of them in preference order, `inherit` (the desk's order), or one of Claude Code's aliases opus, sonnet, haiku or fable, which mean the Claude backend with that model.
- `max_turns` (default 12, at most 120) and `timeout` in seconds (default 300, at most 1,800) are trading-agent's additions. The 30-minute cap keeps a stuck subagent from holding the desk's turn for long, because the desk waits for its reports.
- Names are lower-case with digits, hyphens and underscores, starting with a letter, so they are safe in tool arguments and file names.
