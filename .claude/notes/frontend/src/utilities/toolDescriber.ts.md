# toolDescriber.ts

The summary line copies Claude Code's folded tool groups ("Ran a command, used 3 tools", with "(1 failed)" after a kind that had failures). Tools are grouped into kinds with their own wording, kept in the order they first appear. Claude Code serves the desk's tools over MCP as `mcp__trading_agent__<name>`, so the prefix is dropped before looking a name up. A tool not in the table falls back to "Using <name>" and "used a tool".
