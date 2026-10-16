# read_file_tool.py, write_file_tool.py, edit_file_tool.py

These follow the shape of Claude Code's own Read, Write and Edit tools, which models already use well: numbered lines with a note on where to continue, whole-file writes, and exact-text edits that must match once unless `replace_all` is set. All three use `PathPolicy`, so the rules live in one place.
