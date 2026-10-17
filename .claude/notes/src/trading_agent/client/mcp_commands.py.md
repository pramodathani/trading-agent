# mcp_commands.py

`trading-agent mcp list` starts the manager without the gateway, waits up to 70 seconds for every server's first attempt (enough for `npx -y` to download a package), prints each server's state and tools, then stops. It exits with 1 if any server is not ready, so it can be used in a script.
