# application.py

`Application` reads the command line and the configuration, then either runs the doctor or serves the gateway. It is the only place that builds the components and connects them, so every other class receives what it needs through its constructor.

The server is started with `uvicorn.Config` and `uvicorn.Server` rather than `uvicorn.run`, so that the token-redacting log filter can be installed after uvicorn configures its logging. `uvicorn.run` swallows the `KeyboardInterrupt` that Ctrl+C causes after a graceful shutdown, so `_serve` does the same; under systemd the server is stopped with SIGTERM, which does not raise it.

From milestone 5 the application creates any missing workspace files before every command, so the doctor, `send` and `proposals` all see a complete workspace. Commands other than `serve` log warnings only, to keep their output readable.

From milestone 8 the application builds the secret redactor and the trade journal and hands them to the gateway.

## checkpoints command (milestone 11)

`trading-agent checkpoints list|restore` is handled before the gateway is built, like `proposals`. An unknown `--desk` exits with status 1 rather than creating an empty checkpoint repository for a desk that does not exist.

## Skills (milestone 13)

`trading-agent skills list|import` runs before the gateway is built. The gateway runs `SkillUsageTracker` as a second background worker beside the journal.

## MCP (milestone 13)

`mcp_servers.json` is read once at start-up, before any command that needs it; an invalid file exits with status 2. `trading-agent mcp list` checks the servers on its own. `serve` passes the manager to the desk builder and runs it as a third background worker.

## Packages and hooks (milestone 13, part 3)

`trading-agent packages install|list|remove` runs before the MCP file is read, so a package with a broken MCP file can always be removed. The MCP server list includes installed packages' servers, and `serve` runs the hook runner as a fourth background worker.

## subagents command (milestone 14)

`trading-agent subagents list` runs before the gateway is built, over the user's and packages' definitions.

## Scheduler (milestone 15)

`serve` builds a `CronScheduler` over every desk's schedule and runs it as a fifth background worker.
