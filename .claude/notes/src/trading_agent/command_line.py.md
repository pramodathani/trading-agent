# command_line.py

`-p`, `--desk` and `--output-format` are top-level options, not a subcommand, to match `claude -p`. `--desk` is stored as `chosen_desk` because `send` and `checkpoints` have their own `--desk` with a default, and argparse lets a subparser's default overwrite a top-level value of the same name.

Until the terminal program exists, a bare `trading-agent` still means `serve`. The systemd unit calls `serve` explicitly, so changing the bare command later does not affect the service.
