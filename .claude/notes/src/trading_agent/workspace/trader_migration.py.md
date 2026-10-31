# trader_migration.py

The user renamed the agents from desks to traders while a gateway was already running in dry-run mode with about two weeks of data, and chose to have that data migrated automatically rather than keep the old names in storage or start fresh.

## Why it runs at the start of every command

`Application.run` calls it before `WorkspaceLayout.create_missing`, so no trader folder is created empty before the old one is moved into it. Running it for every command, not only `serve`, means a `doctor` or `checkpoints` run straight after updating sees the migrated data too. When nothing is left to migrate it only checks whether two paths exist, reads three tables' column lists and reads terminal.json, so it costs nothing measurable. The upgrade is still meant to happen with the service stopped, because the old gateway holds the old databases open.

## What is renamed and what is not

Only names that code reads back are changed:

- JSON keys containing "desk", such as `desk`, `desk_pnl` and `text_desk_path`.
- JSON string values that are a single identifier, such as the cron target `"desk"`, the event kind `"desk_started"` and the tool name `"flatten_desk"`.
- Paths under `workspace/desks/` inside JSON values.
- `[desks.<name>]` tables in TradingRules.md. That file is tracked by git, so a normal merge already renames them; the migration covers a copy the user edited without committing.
- The `desk_orders` table and file, and the `desk` columns of the risk ledger, with `ALTER TABLE ... RENAME`, which SQLite has supported since 3.25.
- The checkpoint repositories' `core.worktree`, although `Checkpoints` passes `--work-tree` on every call, so the stale value was harmless.
- The terminal program's remembered `desk` in `~/.local/state/trading-agent/terminal.json`.

Free text is left exactly as written: conversations in sessions, Memory.md, notes and the text inside journal events. Rewriting it could change what a model or the user wrote, and the traders read "desk" in their own history without trouble.

## Safety

Everything that may change is copied first to `workspace/.backups/desk-to-trader-<India time>/`, which is git-ignored. `browser_profile` folders are not copied, because they are Chromium's cache and may contain sockets; they are moved, never rewritten. Files are replaced through a `.migrating` temporary file so a crash never leaves half a file. When a file exists in both the old and the new folder with different content, the new one is kept and the old one stays in `workspace/desks` with a warning, so nothing is overwritten. Every step checks whether it is still needed, so a run interrupted halfway is completed by the next one.

## Rehearsal

Before committing, the migration was run on a copy of the live workspace from 31 October 2026. It took 0.3 seconds, rewrote 62 files under the desks, 12 gateway journals and the Telegram pairing file, and left no "desk" keys or identifier values behind.
