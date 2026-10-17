# add_note_tool.py

`add_note` is the per-turn half of self-improvement (block 34). The plan says "after each turn, one to three notes go to notes/".

## Why a tool and a prompt instruction, not a forced extra call

Forcing a note after every turn would mean a second model call per turn, doubling cost and latency, mostly to record nothing on routine turns such as a heartbeat. Instead the memory section of the system prompt (`prompt_builder.py`) and the tool description ask the desk to call `add_note` after a turn in which it learned something, and to skip routine turns. The "one to three" limit is enforced by the arguments model (`max_length=3`), and each note must be a single line of at most 500 characters, so the file stays a scannable list.

## Format

`notes/YYYY-MM-DD.md` (India date), a `# Notes for <date>` heading when the file is new, then `- HH:MM <note>` bullets. `session_search.py` reads lines starting with `- ` as notes, and the rollover request names this file so the desk can fold it into Memory.md.

## Checkpoint

The desk's files are snapshotted before the note is appended, like `write_file` and `edit_file`. A failed snapshot is logged and the note is still written.

## Verified on 2026-10-17

Asked to record a lesson, Claude called `add_note` with two notes (the lesson and the codeword it was asked to remember), and the checkpoint `before add_note notes/2026-10-17.md` appeared.
