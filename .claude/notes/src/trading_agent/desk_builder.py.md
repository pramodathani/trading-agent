# desk_builder.py

All the parts of a desk are put together here, so that `Application` stays short as later milestones add the prompt builder, memory, the router and the trading tools.

The desk's tools and their `ToolCallExecutor` are built once and handed to whichever backend the desk uses, so Gemma and Claude share the same tools and protections.

Until the model router (milestone 4) exists, a desk uses the first backend in its `backend_order` that has been built: `claude_code` or `ollama`. OpenAI-compatible backends are skipped until milestone 4, and a desk with none falls back to the no-model runner with a warning in the log.

Claude Code runs in `workspace/desks/<desk>/scratch`, a folder with no `CLAUDE.md` above it inside the project, which is ignored by git.

The short built-in system prompt is a stand-in until milestone 5 builds the prompt from `Agents.md`, `User.md`, `TradingRules.md` and the desk's `Persona.md`.
