# skill_importer.py

`trading-agent skills import <folder | file.zip | git URL> [--replace]`.

## Decisions

- **Collections.** Every folder holding a `SKILL.md` is imported, so `~/.hermes/skills/research` brings in all six of its skills in one command. Invalid skills are reported and skipped without stopping the others.
- **No silent overwrite.** An installed skill of the same name is kept unless `--replace` is given.
- **Zip safety.** Every entry is checked to land inside the unpacking folder before anything is extracted; an entry such as `../outside.txt` makes the whole import fail ("zip slip").
- **Git.** `git clone --depth 1` into a temporary folder, which is deleted afterwards; `.git` is never copied into the installed skill.
- **Untrusted text.** An imported skill's instructions go into every trader's index and, when loaded, into the model's context. Part 3 of milestone 13 adds a scan for text that looks like instructions aimed at the model (prompt injection), and the import will warn about it.

## Verified on 2026-10-17

Importing `~/.hermes/skills/research` brought in 6 skills; importing `~/.hermes/skills/email/himalaya` brought in one that `skills list` showed as hidden, "needs program himalaya". The test imports were removed afterwards.

## Warnings and the shared fetcher (milestone 13, part 3)

Each imported skill's `.md` and `.txt` files are scanned for prompt injection, and the import prints a warning per finding while still importing the skill. Fetching from a folder, zip file or git URL now lives in `extensions/source_fetcher.py`, shared with the package installer.
