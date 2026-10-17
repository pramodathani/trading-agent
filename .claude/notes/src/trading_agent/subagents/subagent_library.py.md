# subagent_library.py

Reads `workspace/shared/agents/*.md` and every installed package's `agents/*.md`, afresh each time. On a name clash the user's own file wins. Broken files are skipped and listed by `trading-agent subagents list`, so one bad file never hides the rest.

`index_text` is the "Subagents" section of the desk's prompt: names and descriptions, plus how delegate_task works (tasks run at the same time, each with a fresh conversation that cannot see the desk's, and subagents cannot reach the user or start subagents).
