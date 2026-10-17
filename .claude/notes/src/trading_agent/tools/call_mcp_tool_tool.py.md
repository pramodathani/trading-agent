# call_mcp_tool_tool.py

Runs one MCP tool through the manager with a 120-second wait; the tool's own timeout is 10 seconds longer so the registry's timeout never cuts in first. Errors from the server are returned as tool errors the model can act on. The output is wrapped as data from outside trading-agent.
