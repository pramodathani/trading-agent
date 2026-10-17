# workspace_layout.py

All paths into the workspace live in this one class, so later milestones (memory, journal, skills) add a method here instead of building paths by hand.

`create_missing` never overwrites a file. It runs at every start, so a deleted file is recreated from its template while every edited file is left alone.

A file is still a template while it contains the exact line `Status: template, not filled in yet.`. The prompt builder uses that to decide whether to add the first-run interview, and the interview's instructions tell the model to remove the line from every file it proposes, so accepting the proposals ends the interview.

The templates ship inside the package (`workspace/templates/`) and are read with `importlib.resources`, so they are found whatever the working directory is.

## Milestone 11

`notes_directory`, `sessions_directory` and `checkpoint_repository` were added; `create_missing` now also creates `notes/`. The checkpoint repositories live at `workspace/.checkpoints/<desk>.git`, outside the desk folder, so the desk's file tools cannot reach them and a checkpoint restore cannot rewrite its own history.

The `Agents.md` template's line "Notes and memory tools arrive in later milestones" was replaced with a pointer to the memory section of the prompt. The user's `workspace/shared/Agents.md` was still identical to the template, so the same one-line change was made there.

## Skills (milestone 13)

`installed_skills_directory` (`shared/skills/installed/`, the user's, tracked by the project's git like the other shared files), `agent_skills_directory`, `skill_usage_file` and `skill_ledger_file` (all under `desks/<desk>/skills/`, which `.gitignore` leaves out like the desk's other working files).

## Knowledge, hooks and packages (milestone 13, part 3)

`knowledge_directory` (created at start-up so the user can find it), `knowledge_index_file` (ignored by git), `hooks_directory` and `packages_directory`.
