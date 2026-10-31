# trader_commands.py

Ported from research-agent's analyst commands (commit `6d68744`). The commands go through the running gateway rather than writing folders, because only the gateway can build and start a trader or stop one.

`--models` and `--checks` take comma-separated lists, because argparse lists with `nargs` would swallow the trader's name when options come first. `--heartbeat 0` means no heartbeat, and leaving it out takes the `[traders]` default.

When the gateway cannot be reached, the message says how to start the service, as the other client commands do.
