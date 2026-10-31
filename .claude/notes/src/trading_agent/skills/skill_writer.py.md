# skill_writer.py

Agent-written skills (block 24). The trader writes only through `skill_create`, `skill_patch` and `skill_archive`; `write_file` cannot reach `skills/` (`path_policy.py`), so every skill the trader writes is checked for format.

## Decisions

- **Snapshot first.** Each change takes a checkpoint, as the file tools do; `skills/agent/` is now tracked by `checkpoints.py`. A snapshot with nothing changed since the last one is skipped, so the very first change after a restore has no checkpoint of its own; the restore's own checkpoint covers it.
- **Ledger outside the tracked folder.** `skills/ledger.jsonl` records every create, patch and archive with a reason. The plan put it at `skills/agent/.curator_ledger.jsonl`, but there a checkpoint restore would roll the ledger back too, erasing the record of the change being undone. For the same reason `usage.jsonl` sits beside it.
- **Patch, not rewrite.** A patch replaces exact text that must appear once, like `edit_file`, so a small correction cannot accidentally drop the rest of a skill. The patched text is parsed in a temporary `.patch-check` folder first; a patch that would break the frontmatter or rename the skill is refused and the file is left as it was. Renaming is done by creating a new skill and archiving the old one.
- **Archive, never delete.** `skill_archive` moves the folder to `skills/agent/.archive/<name>/` (with a time stamp if that name is taken).
