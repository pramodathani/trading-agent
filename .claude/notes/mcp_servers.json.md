# mcp_servers.json

The MCP servers every desk can use, in Claude Code's `"mcpServers"` format; see `src/trading_agent/extensions/mcp_server_configuration.py.md`. It is committed empty. The live test of 2026-10-17 used these two servers, which can be pasted back in:

```json
{
  "mcpServers": {
    "everything": {
      "command": "/home/pramod/.nvm/versions/node/v24.21.0/bin/npx",
      "args": ["-y", "@modelcontextprotocol/server-everything"],
      "env": {"PATH": "/home/pramod/.nvm/versions/node/v24.21.0/bin:/usr/local/bin:/usr/bin:/bin"}
    },
    "deepwiki": {
      "type": "http",
      "url": "https://mcp.deepwiki.com/mcp"
    }
  }
}
```
