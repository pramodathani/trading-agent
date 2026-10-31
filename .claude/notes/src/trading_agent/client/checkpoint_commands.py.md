# checkpoint_commands.py

`trading-agent checkpoints list [--trader main] [--limit 20]` and `trading-agent checkpoints restore <id> [--trader main]`. It works directly on the trader's checkpoint repository, so it needs no running gateway, and restoring while the gateway runs is safe: the trader reads Memory.md fresh before every turn.

After a restore it prints the id of the snapshot taken just before, so the user can undo the restore with the same command. The web interface's Checkpoints page (milestone 18) will call the same `Checkpoints` class.
