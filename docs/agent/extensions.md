# Extensions

The traders can be given more than their own tools: tools from MCP servers, your documents, hooks that react to events, and packages that bring any of these, including web apps.

## MCP servers

`mcp_servers.json` uses the `"mcpServers"` format of Claude Code and Claude Desktop, over stdio or streamable HTTP. Each server gets only the environment variables listed for it. A server's tools start out **deferred**: only their names are in a trader's instructions, and the trader loads a tool's full description with `tool_search` and runs it with `call_mcp_tool`. This keeps the local models' smaller context free as servers are added.

<figure class="diagram">
--8<-- "docs/assets/diagrams/mcp.svg"
<figcaption>A trader turn finds a tool with tool_search, then calls it with call_mcp_tool; the client manager keeps one connection per server, here a stdio server and an HTTP one.</figcaption>
</figure>

`bin/trading-agent mcp list` shows each server's state and tools.

## Untrusted text

Text from the web, the knowledge base, MCP servers and imported skills could contain instructions planted for an AI to follow. Such text is wrapped and labelled as data before a model reads it, and the files the traders read are scanned for phrases that look like instructions; the doctor and the importers warn about any they find.

<figure class="diagram">
--8<-- "docs/assets/diagrams/untrusted-text.svg"
<figcaption>Text from the web, MCP servers and the knowledge base passes through the untrusted-text label before a trader reads it. Hooks run as separate programs on events from the event bus, and a package brings skills, servers and hooks together.</figcaption>
</figure>

On 17 October 2026, Qwen ignored an order instruction planted in a web page and warned about it.

## The knowledge base

Documents you put in `workspace/shared/knowledge/`, such as strategy write-ups, broker rules or exchange circulars, are indexed with SQLite's full-text search, and the traders search them with `search_knowledge`.

## Hooks

An executable file in `workspace/shared/hooks/<event>/`, or in a package's `hooks/<event>/`, runs as a separate program each time that event happens. It gets the event as JSON on its standard input, the event's name in `TRADING_AGENT_EVENT` and the trader in `TRADING_AGENT_TRADER`. The folder can be named after any event kind, such as `order`, `risk_decision`, `kill_switch`, `session_started`, `trader_stopped` or `error`, or one of two narrower names: `order_placed` and `risk_rejected`. A failing hook is logged and cannot stop a trader.

## Packages

A **package** is one folder or git repository that holds any of `skills/`, `agents/`, `mcp_servers.json`, `hooks/` and an `app.toml`. `bin/trading-agent packages install <folder or git URL>` copies it into `workspace/shared/packages/` and shows what it brings, and its parts are used from there. No package code runs inside the gateway: its MCP servers, hooks and apps are separate programs.

## Apps

An `app.toml` adds an existing web app to the web page's sidebar, without changing the app. It names the app's page and the systemd user unit that runs it.

```toml
[app]
title = "Sridhara"
description = "A Kite-style trading terminal on UBI: watchlists, charts, option chains and orders."
url = "http://127.0.0.1:8095/"
open_in = "frame"

[service]
unit = "sridhara.service"
unit_file = "%h/Projects/sridhara/services/sridhara.service"
```

<figure class="diagram">
--8<-- "docs/assets/diagrams/apps.svg"
<figcaption>The orange dots are the package being installed, the gateway checking that the app's page answers, and a restart sent to its systemd unit; the blue dots are the answers reaching the sidebar.</figcaption>
</figure>

The gateway shows the app in a frame or a new tab, says whether its page answers, and can start, stop or restart its unit, but only units that installed packages name. `bin/trading-agent apps enable <package>` links and starts a unit that is not set up yet. The `packages/sridhara` package in this repository is the working example.
