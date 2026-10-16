# claude_tool_bridge.py

Claude Code only calls tools over MCP. `create_sdk_mcp_server` makes an MCP server that lives inside this Python process, so a "tool call" from Claude Code is an in-process function call with no network or extra process.

Each tool's handler is a small `ClaudeToolHandler` object rather than a function defined inside a loop, following the user's preference for classes over closures. The SDK accepts any async callable as a handler; `SdkMcpTool` is built directly instead of through the `@tool` decorator for the same reason.

The SDK's handler receives only the arguments, not the tool-use id, so the handler creates its own `ToolCall` id. The current trigger is held on the bridge and set by the turn runner before each turn, so that tool events can be matched to the trigger that caused them.

The SDK turns a returned `is_error: True` into MCP's `isError`, which Claude reads as a failed call.
