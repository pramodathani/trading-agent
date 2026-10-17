# extension_routes.py

These are read-only lists for the Skills, Subagents, MCP and Packages pages, plus checkpoint restore.

Skill usage is read from the desk's usage.jsonl at each request rather than cached, because it changes after every turn that loaded a skill and the file is small.

## Checkpoint ids

The checkpoint id becomes an argument to git. It is checked against the shape of a git hash (7 to 40 hexadecimal characters) before git runs, so a value such as `--help` cannot be passed to git as an option. The answer to a bad id is 422.

A restore first snapshots the current files, so the answer includes `undo_checkpoint_id`: restoring that id undoes the restore.

Installing and removing packages is left to the command line for now, because installing runs the package's own setup and is better watched in a terminal.
