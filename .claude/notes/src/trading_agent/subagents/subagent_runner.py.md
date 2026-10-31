# subagent_runner.py

## One task

1. Find the definition; an unknown name gets a report listing the known ones.
2. Choose backends: the definition's models, or the trader's order; names that match nothing become notes, and if none is usable the trader's order is used.
3. Build the task's tools, a new tool executor with its own loop guard, and the subagent's prompt builder.
4. Build one turn runner per backend through the trader builder's `backend_runner`, the same code the trader's own runners come from, and a fresh `ModelRouter` without a session store, so subagents fall back between models like traders do but keep nothing between tasks.
5. Run the turn under `asyncio.wait_for` with the definition's timeout.
6. Always close the router (stopping any Claude Code process) and the task's bash session.

## Parallel and contained

`run_all` uses `asyncio.gather` over `run_one`, and `run_one` catches its own failures (backend unavailable, timeout, and any other exception at an isolation point), so one task never stops another.

## Events

`subagent_started` (subagent, task, backends, tools) and `subagent_finished` (outcome, backend, seconds, report length). The task's trigger id is on every tool event of the task, which is how the journal links a subagent's tool calls to it. Events carry the trader's name rather than a subagent name, so they go to the trader's journal file.

## Verified on 2026-10-17

Asked to research INFY's news and TCS's candles at once, Claude called delegate_task with two tasks. news_reader and market_researcher started in the same second on Qwen, finished after 103 and 89 seconds, and made 13 and 9 tool calls (market_researcher computed its numbers in its own bash session). Claude then checked the quotes itself and flagged the news figures it could not verify.
