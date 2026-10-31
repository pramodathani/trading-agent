# trader_builder.py

All the parts of a trader are put together here, so that `Application` stays short as later milestones add the prompt builder, memory, the router and the trading tools.

The trader's tools and their `ToolCallExecutor` are built once and handed to whichever backend the trader uses, so Gemma and Claude share the same tools and protections.

Until the model router (milestone 4) exists, a trader uses the first backend in its `backend_order` that has been built: `claude_code` or `ollama`. OpenAI-compatible backends are skipped until milestone 4, and a trader with none falls back to the no-model runner with a warning in the log.

Claude Code runs in `workspace/traders/<trader>/scratch`, a folder with no `CLAUDE.md` above it inside the project, which is ignored by git.

The short built-in system prompt is a stand-in until milestone 5 builds the prompt from `Agents.md`, `User.md`, `TradingRules.md` and the trader's `Persona.md`.

Since milestone 4 every backend in the trader's order becomes a route of the trader's `ModelRouter`, built by kind: `claude_code` as a Claude Code turn runner, `ollama` and `openai_compatible` as an agent loop with its own conversation.

From milestone 5 each trader gets a `PromptBuilder` instead of a fixed prompt, and the `propose_file_change` tool.

From milestone 6 each trader gets its own bash sandbox and terminal, rooted in its scratch folder, and the file, bash and web tools. The trader runtime is given the tool registry so that stopping the trader stops its terminal.

From milestone 7 each trader gets its own browser session, with its profile in `browser_profile/` and screenshots in `scratch/screenshots/`, and the seven browser tools.

From milestone 8 every trader shares one BrokerReader, so the UBI lock covers all traders, and gets the five read-only trading tools.

## The order tools and the shared risk engine (milestone 10)

`_build_order_services` runs once, in the builder's constructor, so every trader built by one builder shares a single risk engine, risk ledger, kill switch and trader order book. The application builds one builder per gateway, which makes the engine account-wide, as the plan requires.

## Milestone 11: memory

`build` now creates, per trader, a `Checkpoints` repository and a `SessionStore`. The store goes to the model router, the checkpoints to `write_file`, `edit_file` and the new `add_note`, and `search_sessions` gets a `SessionSearch` over the trader folder. When the turn runner is a `ModelRouter`, a `SessionKeeper` is built and handed to the trader runtime; a trader without models gets none, because it has no sessions to keep.

## Milestone 12: compression

Each agent-loop runner gets its own `ContextCompressor`, sized by its backend's `context_window`, so Qwen and Gemma each compress at their own 70%. The Claude settings get both thresholds.

## Milestone 13: skills

`build` now makes the bash sandbox itself, with `[sandbox] passed_environment`, so the skill library can check needs against what the sandbox passes. Each trader gets a `SkillLibrary`, a `SkillWriter` (with the trader's checkpoints and ledger), a `SkillCurator` handed to the session keeper, and the tools `load_skill`, `skill_create`, `skill_patch` and `skill_archive`. The library is kept per trader in `_skill_libraries` so `_prompt_builder` can add the index without threading the library through every backend-building method.

## MCP (milestone 13)

The builder receives the gateway's one `McpClientManager`. When at least one server is configured, every trader gets `tool_search` and `call_mcp_tool`, and the prompt builder gets the manager for the tool-name index. With no servers, neither tool is offered, so models are not tempted by tools that cannot work.

## Milestone 13, part 3

Every trader gets `search_knowledge`, over one knowledge base shared by all traders, and its skill library includes the skills of installed packages.

## Milestone 14: subagents

`backend_runner` (public now) takes the prompt builder and round limit as arguments, so the subagent runner builds its turn runners with the same code as the trader, through `functools.partial(self.backend_runner, trader_configuration)`. Each trader gets a `SubagentRunner` and `delegate_task`; the toolbox is built from the trader's tools before delegate_task is added, so it can never reach a subagent. The prompt builder gets the subagent library for the Subagents section.

## Milestone 15: scheduling

The builder owns one `MarketCalendar` and one `ExchangeHours` built on it, shared by the risk engine and the scheduler. Each trader gets a `CronJobStore`, its built-in jobs, and the tools cron_create, cron_list, cron_delete, schedule_wakeup and send_message. `trader_schedule` returns what the scheduler needs for a built trader: its store, built-in jobs, a command runner on its sandbox, and its subagent runner.

## Milestone 15, part 2

Each trader gets a `PriceAlertStore` and the tools set_price_alert and cancel_price_alert. `market_watcher` builds the watcher over the built traders, sharing the order services' order book and risk engine, the alert stores and the exchange hours. The builder takes the usage tracker and hands it to every trader.

## Milestone 16: several traders

Traders were already built one per `[[traders]]` entry, each with its own queue, router, session store, tools and memory. The builder now passes each trader's scheduled checks to its built-in jobs, the other enabled traders' names to its prompt, and a `MarketStatus` to its runtime.

## Milestone 17: parts for the API

While building each trader, the builder records its stores and tools in a `TraderParts`, and `shared_parts()` returns the shared objects in a `SharedParts`. The gateway's API reads both. The kill switch is kept on the builder for this reason.

## Steering inboxes (milestone 18)

The builder makes one steering inbox per trader and gives it to the trader's runtime and to the trader's own runners, through `backend_runner`'s `steering_inbox` argument. Subagent runners are built through the same method without it, so they cannot be steered.

## The attachment store, since 2026-10-17

The builder creates the one `AttachmentStore` and hands it out in the shared parts.

`send_image` and `view_image` are given every trader's file rules (`PathPolicy`), so they read exactly what `read_file` can. `send_image` also gets the one shared `AttachmentStore`, the same object the upload routes and Telegram use, so a picture a trader sends is found by `GET /api/traders/{trader}/attachments/{id}` like any upload.

## Command parts, since 2026-10-18

Each trader's `TraderRuntime` gets a `slash_commands.CommandParts` with the shared subagent library, a `JournalReader` over the trader's journal folder, and the trader's own subagent runner, taken from `_schedule_parts` where `_executor` stored it. The commands `/subagents` and `/review` read these.
