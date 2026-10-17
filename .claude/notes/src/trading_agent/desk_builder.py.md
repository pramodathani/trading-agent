# desk_builder.py

All the parts of a desk are put together here, so that `Application` stays short as later milestones add the prompt builder, memory, the router and the trading tools.

The desk's tools and their `ToolCallExecutor` are built once and handed to whichever backend the desk uses, so Gemma and Claude share the same tools and protections.

Until the model router (milestone 4) exists, a desk uses the first backend in its `backend_order` that has been built: `claude_code` or `ollama`. OpenAI-compatible backends are skipped until milestone 4, and a desk with none falls back to the no-model runner with a warning in the log.

Claude Code runs in `workspace/desks/<desk>/scratch`, a folder with no `CLAUDE.md` above it inside the project, which is ignored by git.

The short built-in system prompt is a stand-in until milestone 5 builds the prompt from `Agents.md`, `User.md`, `TradingRules.md` and the desk's `Persona.md`.

Since milestone 4 every backend in the desk's order becomes a route of the desk's `ModelRouter`, built by kind: `claude_code` as a Claude Code turn runner, `ollama` and `openai_compatible` as an agent loop with its own conversation.

From milestone 5 each desk gets a `PromptBuilder` instead of a fixed prompt, and the `propose_file_change` tool.

From milestone 6 each desk gets its own bash sandbox and terminal, rooted in its scratch folder, and the file, bash and web tools. The desk runtime is given the tool registry so that stopping the desk stops its terminal.

From milestone 7 each desk gets its own browser session, with its profile in `browser_profile/` and screenshots in `scratch/screenshots/`, and the seven browser tools.

From milestone 8 every desk shares one BrokerReader, so the UBI lock covers all desks, and gets the five read-only trading tools.

## The order tools and the shared risk engine (milestone 10)

`_build_order_services` runs once, in the builder's constructor, so every desk built by one builder shares a single risk engine, risk ledger, kill switch and desk order book. The application builds one builder per gateway, which makes the engine account-wide, as the plan requires.

## Milestone 11: memory

`build` now creates, per desk, a `Checkpoints` repository and a `SessionStore`. The store goes to the model router, the checkpoints to `write_file`, `edit_file` and the new `add_note`, and `search_sessions` gets a `SessionSearch` over the desk folder. When the turn runner is a `ModelRouter`, a `SessionKeeper` is built and handed to the desk runtime; a desk without models gets none, because it has no sessions to keep.

## Milestone 12: compression

Each agent-loop runner gets its own `ContextCompressor`, sized by its backend's `context_window`, so Qwen and Gemma each compress at their own 70%. The Claude settings get both thresholds.

## Milestone 13: skills

`build` now makes the bash sandbox itself, with `[sandbox] passed_environment`, so the skill library can check needs against what the sandbox passes. Each desk gets a `SkillLibrary`, a `SkillWriter` (with the desk's checkpoints and ledger), a `SkillCurator` handed to the session keeper, and the tools `load_skill`, `skill_create`, `skill_patch` and `skill_archive`. The library is kept per desk in `_skill_libraries` so `_prompt_builder` can add the index without threading the library through every backend-building method.

## MCP (milestone 13)

The builder receives the gateway's one `McpClientManager`. When at least one server is configured, every desk gets `tool_search` and `call_mcp_tool`, and the prompt builder gets the manager for the tool-name index. With no servers, neither tool is offered, so models are not tempted by tools that cannot work.

## Milestone 13, part 3

Every desk gets `search_knowledge`, over one knowledge base shared by all desks, and its skill library includes the skills of installed packages.

## Milestone 14: subagents

`backend_runner` (public now) takes the prompt builder and round limit as arguments, so the subagent runner builds its turn runners with the same code as the desk, through `functools.partial(self.backend_runner, desk_configuration)`. Each desk gets a `SubagentRunner` and `delegate_task`; the toolbox is built from the desk's tools before delegate_task is added, so it can never reach a subagent. The prompt builder gets the subagent library for the Subagents section.

## Milestone 15: scheduling

The builder owns one `MarketCalendar` and one `ExchangeHours` built on it, shared by the risk engine and the scheduler. Each desk gets a `CronJobStore`, its built-in jobs, and the tools cron_create, cron_list, cron_delete, schedule_wakeup and send_message. `desk_schedule` returns what the scheduler needs for a built desk: its store, built-in jobs, a command runner on its sandbox, and its subagent runner.

## Milestone 15, part 2

Each desk gets a `PriceAlertStore` and the tools set_price_alert and cancel_price_alert. `market_watcher` builds the watcher over the built desks, sharing the order services' order book and risk engine, the alert stores and the exchange hours. The builder takes the usage tracker and hands it to every desk.

## Milestone 16: several desks

Desks were already built one per `[[desks]]` entry, each with its own queue, router, session store, tools and memory. The builder now passes each desk's scheduled checks to its built-in jobs, the other enabled desks' names to its prompt, and a `MarketStatus` to its runtime.

## Milestone 17: parts for the API

While building each desk, the builder records its stores and tools in a `DeskParts`, and `shared_parts()` returns the shared objects in a `SharedParts`. The gateway's API reads both. The kill switch is kept on the builder for this reason.

## Steering inboxes (milestone 18)

The builder makes one steering inbox per desk and gives it to the desk's runtime and to the desk's own runners, through `backend_runner`'s `steering_inbox` argument. Subagent runners are built through the same method without it, so they cannot be steered.

## The attachment store, since 2026-10-17

The builder creates the one `AttachmentStore` and hands it out in the shared parts.
