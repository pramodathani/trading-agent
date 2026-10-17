# mcp_server_configuration.py

Reads `mcp_servers.json` (block 25), whose path is `mcp_servers_file` in trading_agent.toml.

## Decisions

- **Claude Code's format.** The `"mcpServers"` object of Claude Code and Claude Desktop, so a server's documented snippet can be pasted in. `"type": "streamable-http"` is accepted as a spelling of `"http"`.
- **No SSE.** The old SSE transport is refused with a message, because the MCP specification replaced it with streamable HTTP and current servers offer both.
- **`${NAME}` and `${NAME:-default}`** are expanded in the command, arguments, cwd, env values, URL and headers, as Claude Code does, so a token can stay in `.env` instead of the JSON file. An unset variable without a default becomes an empty string rather than an error, so a server that does not need it still starts.
- **Errors stop the gateway.** A file that is not valid JSON or has an invalid server makes `serve` exit with status 2, like an invalid trading_agent.toml, because a silently missing server is harder to notice than a refusal to start. The doctor reports the same error.
- A missing file means no servers. The repository's `mcp_servers.json` is an empty list.

## Package servers (milestone 13, part 3)

`read_with_packages` adds each installed package's servers after the project's. A package server whose name is taken is left out with a warning, so the user's file always wins, and a stdio server without a `cwd` starts in its package's folder so it can run a program shipped inside the package.
