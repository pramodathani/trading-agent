# mcp_client_manager.py

Connections to MCP servers (block 25) and the data behind tool search (block 22). Built on the MCP Python SDK 2.3.0, whose client API differs from version 1 (for example `FastMCP` became `MCPServer`, and result fields are snake_case such as `is_error` and `input_schema`).

## One connection per server, shared by all traders

Each `McpServerConnection` runs in its own task, owned by the manager, which the gateway runs as a background worker beside the journal. The SDK's transports use anyio task groups that must be entered and exited in the same task, so the connection task enters them and keeps them open; trader tasks only send requests through the session, which is safe from any task.

## Environment isolation

A stdio server gets the SDK's safe defaults (HOME, LOGNAME, PATH, SHELL, TERM, USER) plus its own `env`, nothing else. Verified live on 2026-10-17: the `everything` server's `get-env` returned 30 names, the defaults plus variables that `npx` itself adds, and no `TRADING_AGENT_*`, `TRADINGMACHINE_*` or Claude token. A consequence: a server launched through nvm's `npx` needs nvm's `bin` folder in its own `PATH`, because the gateway's non-interactive shell does not load nvm. The first live attempt failed with "No such file or directory: 'npx'" for exactly that reason.

## Failures

A server that fails to start, or whose connection breaks during a call, is marked failed and retried after 30 s, 60 s, then every 300 s, like the model router's waits; the other servers are unaffected. A broken connection is detected when a call raises anything other than the SDK's `MCPError` (which means the server answered with an error, so the connection is fine). The catch-all in `run` is an isolation point, marked `noqa: BLE001`.

## Why not one native tool per MCP tool

The plan said MCP tools start "deferred", listed by name, with `tool_search` loading a description. The traders get exactly two tools, `tool_search` and `call_mcp_tool`, instead of the MCP tools themselves being added to their tool lists. Reasons:

- The agent loop could add tool definitions between rounds, but Claude's tools are fixed when its Claude Code process starts, so native dynamic tools would work differently per backend.
- Every MCP call then goes through trading-agent's own executor: the journal, the loop guard, secret redaction and the event stream see it like any other tool.

The plan also said the same server list would be passed to Claude. It is not: Claude reaches MCP servers through the same two tools as every other backend, for the reasons above, and because the allowlist hook would refuse Claude Code's own MCP tools anyway.

## Output

Text is joined; the first PNG image is passed on as a picture the model can see; other content types are named and left out; structured content is used when there is no text. `call_mcp_tool` labels the output as data from outside trading-agent, and the prompt section says never to follow instructions found in it. Part 3 of milestone 13 adds the injection scanner.
