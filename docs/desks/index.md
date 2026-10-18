# The desks

A **desk** is one independent agent inside the gateway. Each desk has its own persona, its own models in its own order, its own schedule, its own conversation and memory, and its own queue of things to do. Desks run side by side, so the scalper never waits for the positional desk, but each desk handles one thing at a time, so it never runs two turns at once.

All desks share one account at UBI and one risk engine. The risk engine gives each stock to one desk at a time, applies each desk's own limits, and stops everyone at the account's loss limits.

## The four desks

| Desk | Style | Products | Models, in order | Wakes up |
|---|---|---|---|---|
| general | General purpose, whatever its strategy needs | any | Claude Opus, DeepSeek, Qwen, Gemma | When you message it, and at its alerts and fills |
| intraday | Minutes to hours, flat by 15:15 | `mis` | Claude Opus, DeepSeek, Qwen, Gemma | Heartbeat every 10 minutes in market hours; checks at 09:05, 15:05 and 15:35 |
| scalper | Seconds to minutes, entering and leaving through UBI's bracket orders | `mis` | Claude Sonnet, DeepSeek, Qwen, Gemma | Heartbeat every 2 minutes in market hours; checks at 09:10 and 15:05 |
| positional | Days to weeks | `cnc`, `nrml` | Claude Opus, DeepSeek, Qwen, Gemma | Checks at 08:45, 12:30 and 15:40; no heartbeat |

The scalper starts with Claude Sonnet at low effort rather than Opus, because it wakes every two minutes and would otherwise use up Opus's share of the Max subscription's limits. It trades in two layers: it decides the instrument, the direction, the entry, the target and the stop, and UBI's bracket orders do the entry and exit in real time, because one decision of a model takes seconds.

## Strategies

The strategies belong in TradingRules.md, and today only the scalper has one. Every desk without a written strategy for its style watches and reports, but opens nothing.

The scalper's strategy, which the desk proposed and you approved on 18 October 2026, buys NIFTY weekly options only, as `mis`, always entered with a bracket order. It has two setups, and the table below summarises them.

| Setup | When | Signal | Bracket on the option |
|---|---|---|---|
| A: opening-range breakout | 09:30 to 11:00 | A 5-minute NIFTY candle closes outside the 09:15 to 09:30 range | Stop 15% below the entry premium, target 25% above |
| B: momentum candle | 09:30 to 11:00 and 13:30 to 14:45 | A strong 5-minute candle in the direction of the day's trend | Stop 10% below, target 15% above |

Both setups risk 1% of the balance per trade, hold at most two positions at once, stop after three losses in a row or at the desk's 3% daily loss limit, and are flat by 15:05. After ten dry-run trading days the desk reviews the numbers and proposes changes. TradingRules.md holds the full rules, including the liquidity filter and the order types each desk may use.

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
