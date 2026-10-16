# desk_builder.py

All the parts of a desk are put together here, so that `Application` stays short as later milestones add the prompt builder, memory, the router and the trading tools.

In milestone 2 a desk uses the first `ollama` backend in its `backend_order`. Other kinds are skipped until their backends exist (Claude in milestone 3, OpenAI-compatible in milestone 4), and a desk with none falls back to the no-model runner with a warning in the log.

The short built-in system prompt is a stand-in until milestone 5 builds the prompt from `Agents.md`, `User.md`, `TradingRules.md` and the desk's `Persona.md`.
