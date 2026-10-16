# claude_tool_allowlist_hook.py

`tools=[]` already switches off every built-in Claude Code tool (the SDK passes `--tools ""`), and the probe on 2026-10-16 showed the session's tool list held only `mcp__trading_agent__get_time`. The hook is a second, independent lock, because a built-in Bash or file tool would bypass the bwrap sandbox and, later, the risk engine. Claude Code runs PreToolUse hooks even under `bypassPermissions`, and a deny decision there cannot be overridden by the model.
