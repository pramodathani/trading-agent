# tool_search_tool.py

Block 22. Ranks the ready MCP tools by how many query words appear in their server name, tool name and description; a query equal to a server's name lists all its tools; no match lists every tool's `server/name`, so the desk can recover in one step. Each result includes the full JSON argument schema, which is what the desk needs to build `call_mcp_tool`'s arguments.

Verified on 2026-10-17: Qwen searched "get-sum" (it knew the name from the prompt's index), then called it correctly with `{"a": 17, "b": 25}`.
