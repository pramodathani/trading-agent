# schedule_routes.py

The job list joins three sources: the built-in jobs from trading_agent.toml (heartbeat, rollover, scheduled checks), the jobs the trader or user created, and the run log. Each job gets its next three runs from the scheduler itself, so the list shows exactly what the scheduler will do, including holidays and market hours.

A new job takes `instructions` or `command`, never both, the same split `cron_create` uses since the milestone 15 fix where Qwen put a sentence in the command field. Jobs created here are marked `created_by: user`.

Built-in jobs cannot be deleted here, because they would come back at the next start; the answer says to change trading_agent.toml instead. On 2026-10-17 the live test showed this answer on the scalper trader, and "No job" on the main trader, which has no heartbeat.

"Run now" starts the job through the scheduler's normal path (`CronScheduler.run_now`), so it is recorded in runs.jsonl and its result arrives as a `cron_result` event like any other run. The heartbeat's own rule still applies: a heartbeat started while the trader is busy is skipped.
