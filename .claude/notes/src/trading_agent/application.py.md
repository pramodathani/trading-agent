# application.py

`Application` reads the command line and the configuration, then either runs the doctor or serves the gateway. It is the only place that builds the components and connects them, so every other class receives what it needs through its constructor.

The server is started with `uvicorn.Config` and `uvicorn.Server` rather than `uvicorn.run`, so that the token-redacting log filter can be installed after uvicorn configures its logging. `uvicorn.run` swallows the `KeyboardInterrupt` that Ctrl+C causes after a graceful shutdown, so `_serve` does the same; under systemd the server is stopped with SIGTERM, which does not raise it.
