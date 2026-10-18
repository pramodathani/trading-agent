# command_line.py

`-p`, `--desk` and `--output-format` are top-level options, not a subcommand, to match `claude -p`. `--desk` is stored as `chosen_desk` because `send` and `checkpoints` have their own `--desk` with a default, and argparse lets a subparser's default overwrite a top-level value of the same name.

Since 2026-10-18 a bare `trading-agent` opens the terminal program, as a bare `claude` does, and `serve` must be named. The systemd unit (`deploy/trading-agent.service`) and every page of the docs already called `serve` explicitly, so nothing that starts the gateway changed. `--desk` also picks the desk the terminal program opens on.
