# subagent_toolbox.py

## The default set

Without a `tools` list a subagent gets read-only tools: time, files (reading), the web, instruments, quotes, candles, portfolio, orders (reading), past sessions, the knowledge base, skills and MCP tools. Only tools the trader actually has are given, so the default works whether or not MCP servers are configured.

## Shared tools

Most tools are the trader's own objects, shared with its subagents. That matters for orders: a subagent that lists `place_order` places it through the trader's risk engine under the trader's name, so all limits and stock ownership still apply.

## Never given

- `delegate_task`, so a subagent cannot start subagents (the plan's rule). The trader builder also builds the toolbox before adding delegate_task to the trader's tools, so it is not even available to name.
- The browser tools, because each trader has one Chrome profile and one browser session, which two tasks cannot drive at once.

## Bash

The bash tools are rebuilt for each task on a fresh `BashSession` in the trader's sandbox, so parallel tasks never type into one shell; the runner closes the session afterwards.
