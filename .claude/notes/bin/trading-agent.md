# bin/trading-agent

The launcher, written the same way as `sridhara/bin/sridhara`. It changes into the project folder first, so `trading_agent.toml` and `.env` are found by their relative names whatever folder the command is typed from. `exec` replaces the shell with Python, so the process number belongs to Python itself and signals from systemd or Ctrl+C reach the server directly.
