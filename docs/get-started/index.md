# Get started

This section takes trading-agent from a fresh checkout to a running service. It assumes the machine already runs UBI on `127.0.0.1:8080` and has the `tradingmachine` project next to this one, as described in their own documentation.

The steps below are in the order you follow them.

1. [Installation](installation.md): the Python environment, the packages, Ollama's models, Claude Code's token and the web page.
2. [Configuration](configuration.md): every setting in `trading_agent.toml` and every secret in `.env`.
3. [First run](first-run.md): the doctor, the gateway, the web page and a first message.
4. [The service](service.md): running it under systemd so it starts at boot and survives a crash.

After that, [Going live](../going_live.md) is the plan for the first trading day.
