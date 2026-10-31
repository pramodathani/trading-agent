# read_file_tool.py, write_file_tool.py, edit_file_tool.py

These follow the shape of Claude Code's own Read, Write and Edit tools, which models already use well: numbered lines with a note on where to continue, whole-file writes, and exact-text edits that must match once unless `replace_all` is set. All three use `PathPolicy`, so the rules live in one place.

## Checkpoints (milestone 11)

With a `Checkpoints` object, the tool snapshots the trader's files after its checks pass and just before it writes, with the message `before edit_file <path>`. `write_file_tool.py` does the same with `before write_file <path>`. The two tools keep their own copy of the small `_snapshot` method rather than sharing a base class, following the rule that similar cases stay self-contained. A failed snapshot is logged and the write still happens.
