# checkpoints.py

Checkpoints are block 31 of the plan: snapshots of each desk's agent-writable files, so anything the desk writes can be undone.

## Design

- One git repository per desk, at `workspace/.checkpoints/<desk>.git`, created on first use. It uses `--git-dir` and `--work-tree`, so the desk folder itself holds no `.git`, and the project's own repository never sees the snapshots (`workspace/.checkpoints/` is in `.gitignore`).
- Only `Memory.md`, `memory/` and `notes/` are tracked. The repository's `info/exclude` ignores everything (`/*`) and then un-ignores those three. That lets `git add --all` pick up additions, edits and deletions in one command without naming paths that might not exist (naming a missing path makes `git add` fail).
- `scratch/`, `journal/`, `sessions/`, `proposals/` and `browser_profile/` are never touched by a restore. Scratch is temporary and can be large; the journal is an append-only record that must never be rewritten; sessions are code-owned.
- A snapshot is taken *before* each write, so every checkpoint is "the state just before change X". Its message says what was about to happen, such as `before write_file Memory.md`. A snapshot with nothing changed is skipped.
- `restore` first snapshots the current state, then runs `git restore --source=<id> --staged --worktree -- .`. `git restore` works in no-overlay mode, so tracked files that did not exist at the checkpoint are deleted. The restore is then committed as `restored <id>`. Because of the snapshot taken first, every restore can itself be undone, and the command line prints the id to use.
- The user's global and system git configuration is switched off for these commands (`GIT_CONFIG_GLOBAL=/dev/null`, `GIT_CONFIG_NOSYSTEM=1`), and signing is turned off. A global hook or `commit.gpgsign = true` would otherwise slow down or break every write the desk makes.
- A `threading.Lock` serialises git commands on one repository. The agent loop runs a turn's tool calls together with `asyncio.gather`, and the tools call `snapshot` through `asyncio.to_thread`, so two snapshots could otherwise race for git's `index.lock`.

## Failure policy

A failed snapshot is logged by the calling tool, and the write still goes ahead. Losing one undo point is better than a desk that cannot record a note or update its memory because git failed.

## Why the bash tool needs no hook

The bash sandbox mounts the desk folder read-only except `scratch/` (`bash_sandbox.py`), so the only ways to change tracked files are `write_file`, `edit_file` and `add_note`, and all three snapshot first. Milestone 13's skill writer and curator will add `skills/agent/` to the tracked paths and snapshot before they run.

## Verified on 2026-10-17

The live test took `fdcf6c1 before add_note notes/2026-10-17.md` and `378531b before write_file Memory.md`, then `trading-agent checkpoints restore fdcf6c1` returned Memory.md to its template and removed the day's notes file, while `notes/tool-test.md`, which already existed at that checkpoint, stayed.

## skills/agent/ (milestone 13)

`skills/agent/` is now tracked, through ignore rules that un-ignore `/skills/` and then ignore everything in it except `agent/`. `_ensure_repository` rewrites the ignore rules whenever they differ from the current ones, so a repository created by milestone 11 starts tracking skills without being recreated.
