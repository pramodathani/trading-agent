# The desks

A **desk** is one independent agent inside the gateway. Each desk has its own persona, its own models in its own order, its own schedule, its own conversation and memory, and its own queue of things to do. Desks run side by side, so the scalper never waits for the positional desk, but each desk handles one thing at a time, so it never runs two turns at once.

All desks share one account at UBI and one risk engine. The risk engine gives each stock to one desk at a time, applies each desk's own limits, and stops everyone at the account's loss limits.

## The four desks

| Desk | Style | Products | Models, in order | Wakes up |
|---|---|---|---|---|
| main | General purpose, whatever its strategy needs | any | Claude, Qwen, Gemma | When you message it, and at its alerts and fills |
| intraday | Minutes to hours, flat by 15:15 | `mis` | Claude, Qwen, Gemma | Heartbeat every 10 minutes in market hours; checks at 09:05, 15:05 and 15:35 |
| scalper | Seconds to minutes, entering and leaving through UBI's bracket orders | `mis` | Qwen, Gemma, Claude | Heartbeat every 2 minutes in market hours; checks at 09:10 and 15:05 |
| positional | Days to weeks | `cnc`, `nrml` | Claude, Qwen, Gemma | Checks at 08:45, 12:30 and 15:40; no heartbeat |

The scalper puts the local models first because they are fast, free and have no usage limits, and it trades in two layers: it decides the instrument, the direction, the entry, the target and the stop, and UBI's bracket orders do the entry and exit in real time, because one decision of a model takes seconds.

Every desk without a written strategy for its style watches and reports, but opens nothing. The strategies belong in TradingRules.md.

## What every message starts with

Each message a desk receives starts with one line that tells it where it is in time: the India date and time, what woke it, and the market's state, such as "NSE closed today (weekend); next trading day Mon 19 Oct, holiday ahead: Tue 20 Oct Dussehra". Those facts change every turn, so they are in the message rather than in the instructions.

## Where each desk keeps its things

```text
workspace/desks/<desk>/
├── Persona.md        yours: style, holding period, products, cadence
├── Memory.md         the desk's lasting lessons
├── memory/  notes/   the desk's own files and daily notes
├── skills/agent/     the skills the desk wrote itself
├── sessions/         one conversation log per trading day
├── journal/          every event, one file per day
├── cron/             the desk's scheduled jobs and their runs
├── proposals/        changes it suggests to your files
└── scratch/          the one folder its bash sandbox may write
```

Each desk's own files are snapshotted before every change, in `workspace/.checkpoints/<desk>.git`, so any change can be undone on the Checkpoints page.
