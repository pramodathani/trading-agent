# subagent_toolbox.py

## The default set

Without a `tools` list a subagent gets read-only tools: time, files (reading), the web, instruments, quotes, candles, portfolio, orders (reading), past sessions, the knowledge base, skills and MCP tools. Only tools the desk actually has are given, so the default works whether or not MCP servers are configured.

## Shared tools

Most tools are the desk's own objects, shared with its subagents. That matters for orders: a subagent that lists `place_order` places it through the desk's risk engine under the desk's name, so all limits and stock ownership still apply.

## Never given

- `delegate_task`, so a subagent cannot start subagents (the plan's rule). The desk builder also builds the toolbox before adding delegate_task to the desk's tools, so it is not even available to name.
- The browser tools, because each desk has one Chrome profile and one browser session, which two tasks cannot drive at once.

## Bash

The bash tools are rebuilt for each task on a fresh `BashSession` in the desk's sandbox, so parallel tasks never type into one shell; the runner closes the session afterwards.
