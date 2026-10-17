# application.py

`Application` reads the command line and the configuration, then either runs the doctor or serves the gateway. It is the only place that builds the components and connects them, so every other class receives what it needs through its constructor.

The server is started with `uvicorn.Config` and `uvicorn.Server` rather than `uvicorn.run`, so that the token-redacting log filter can be installed after uvicorn configures its logging. `uvicorn.run` swallows the `KeyboardInterrupt` that Ctrl+C causes after a graceful shutdown, so `_serve` does the same; under systemd the server is stopped with SIGTERM, which does not raise it.

From milestone 5 the application creates any missing workspace files before every command, so the doctor, `send` and `proposals` all see a complete workspace. Commands other than `serve` log warnings only, to keep their output readable.

From milestone 8 the application builds the secret redactor and the trade journal and hands them to the gateway.

## checkpoints command (milestone 11)

`trading-agent checkpoints list|restore` is handled before the gateway is built, like `proposals`. An unknown `--desk` exits with status 1 rather than creating an empty checkpoint repository for a desk that does not exist.

## Skills (milestone 13)

`trading-agent skills list|import` runs before the gateway is built. The gateway runs `SkillUsageTracker` as a second background worker beside the journal.
