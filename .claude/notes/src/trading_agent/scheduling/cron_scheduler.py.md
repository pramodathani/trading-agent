# cron_scheduler.py

## Loop

`run` catches up once, then calls `tick` and sleeps until the earliest next run, at most 30 seconds, so a job created by a tool is noticed within half a minute. `tick` and `catch_up` are separate methods so tests can drive them with a fixed clock.

## When a job is due

Each job's next run is counted from the latest of: when the scheduler started, the job's last recorded run, and its creation time. So a newly created job never runs for a time before it existed, and a run is never repeated. The run is recorded in state.json and runs.jsonl before it starts, so a crash during a run cannot repeat it.

## Catch-up

At start, a job with `catch_up` whose previous scheduled run was within 24 hours, after its creation, and later than its last recorded run, is started once, marked as running late. Verified on 2026-10-17: with the gateway stopped from 11:12:13 to 11:13:39, the per-minute test job made up the 11:13 run once at start, then carried on at 11:14. The rollover also caught up Friday's missed 15:45 run on the first start, which is the intended behaviour.

## What each job does

- Agent job for the desk: a trigger in the desk's queue (source `cron`, or `heartbeat`), prefixed with the job's name and id, so it never runs beside one of the desk's turns. The built-in rollover's text is `/rollover`, a command, so it runs without a model.
- Heartbeat: skipped and recorded as skipped when the desk is busy or has triggers waiting, so heartbeats never pile up behind a long turn.
- Subagent job (`target: subagent:<name>`) and command job: run as background tasks; the result is published as `cron_result`.
- One-off job: deleted from jobs.json when it starts.
- `deliver_url`: the result (the desk's answer for an agent job, read from its `text` event; the report or output otherwise) is POSTed as JSON with secrets masked; a failure is logged.

## Events

`cron_fired` (job, kind, target, scheduled time, whether catching up) and `cron_result`. Hooks can react to both.

## Run now (milestone 17)

`run_now` starts a job through the same `_start` the timer uses, with `catching_up` false, so a run started from the web page is recorded and reported exactly like a scheduled one.
