# prompt_builder.py

The prompt is rebuilt before every turn, so an edit to a workspace file reaches the desk on its next turn without a restart. It holds only slow-changing text: the desk's name, the mode and the files. The time and the trigger go in the user message (see `desk_runtime.py`), because anything that changes every turn in the system prompt would make the model's prompt cache miss every time.

The order is Agents.md, Persona.md, User.md, TradingRules.md, Memory.md: general rules first, then the desk's own style, then the user and the hard limits, then lessons. The caps (20,000 characters per file, 60,000 in total) come from OpenClaw's bootstrap-file limits, and keep a runaway Memory.md from filling Gemma's 32,768-token context.

The fingerprint is the first 16 hex digits of the text's SHA-256. The Claude runner compares it with the fingerprint its Claude Code process was started with, and restarts the process (resuming the same session) when they differ, because Claude Code takes its system prompt only at start.

## How your memory works (milestone 11)

A fixed section after the header explains sessions, the rollover, `add_note`, `search_sessions` and checkpoints. It lives in code rather than in `Agents.md` because it describes how the program works, which the user should not have to keep in step with the code. The header line now mentions it. Changing it changed every desk's prompt fingerprint once, so Claude received the new instructions inside its next message.
