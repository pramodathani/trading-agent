# tool_describer.py

A port of `frontend/src/utilities/toolDescriber.ts`. The tables were generated from the TypeScript file on 2026-10-18 (16 kinds, 47 tools), so a tool added to one should be added to the other. Claude Code serves the desk's tools over MCP and names them `mcp__trading_agent__<tool>`, which is why `base_name` strips everything up to the last `__`.
