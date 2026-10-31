# The traders

A **trader** is one independent agent inside the gateway. Each trader has its own persona, its own models in its own order, its own schedule, its own conversation and memory, and its own queue of things to do. Traders run side by side, so the scalper never waits for the positional trader, but each trader handles one thing at a time, so it never runs two turns at once.

All traders share one account at UBI and one risk engine. The risk engine gives each stock to one trader at a time, applies each trader's own limits, and stops everyone at the account's loss limits.

## The four starter traders

A fresh workspace starts with general, and this machine also has the three traders below it. The traders you create afterwards join them, as [Creating a trader](#creating-a-trader) describes.

| Trader | Style | Products | Models, in order | Wakes up |
|---|---|---|---|---|
| general | General purpose, whatever its strategy needs | any | Claude Opus, DeepSeek, Qwen, Gemma | When you message it, and at its alerts and fills |
| intraday | Minutes to hours, flat by 15:15 | `mis` | Claude Opus, DeepSeek, Qwen, Gemma | Heartbeat every 10 minutes in market hours; checks at 09:05, 15:05 and 15:35 |
| scalper | Seconds to minutes, entering and leaving through UBI's bracket orders | `mis` | Claude Sonnet, DeepSeek, Qwen, Gemma | Heartbeat every 2 minutes in market hours; checks at 09:10 and 15:05 |
| positional | Days to weeks | `cnc`, `nrml` | Claude Opus, DeepSeek, Qwen, Gemma | Checks at 08:45, 12:30 and 15:40; no heartbeat |

The scalper starts with Claude Sonnet at low effort rather than Opus, because it wakes every two minutes and would otherwise use up Opus's share of the Max subscription's limits. It trades in two layers: it decides the instrument, the direction, the entry, the target and the stop, and UBI's bracket orders do the entry and exit in real time, because one decision of a model takes seconds.

## Strategies

The strategies belong in TradingRules.md, and today only the scalper has one. Every trader without a written strategy for its style watches and reports, but opens nothing.

The scalper's strategy, which the trader proposed and you approved on 18 October 2026, buys NIFTY weekly options only, as `mis`, always entered with a bracket order. It has two setups, and the table below summarises them.

| Setup | When | Signal | Bracket on the option |
|---|---|---|---|
| A: opening-range breakout | 09:30 to 11:00 | A 5-minute NIFTY candle closes outside the 09:15 to 09:30 range | Stop 15% below the entry premium, target 25% above |
| B: momentum candle | 09:30 to 11:00 and 13:30 to 14:45 | A strong 5-minute candle in the direction of the day's trend | Stop 10% below, target 15% above |

Both setups risk 1% of the balance per trade, hold at most two positions at once, stop after three losses in a row or at the trader's 3% daily loss limit, and are flat by 15:05. After ten dry-run trading days the trader reviews the numbers and proposes changes. TradingRules.md holds the full rules, including the liquidity filter and the order types each trader may use.

## Where each trader's settings live

Each trader is described by its own record, `workspace/traders/<name>/trader.toml`, which holds its mandate (what it trades and how), its models, its heartbeat, its scheduled checks and whether it is retired. `trading_agent.toml` no longer lists the traders; its `[traders]` table only holds the defaults that a new trader gets, as [Configuration](../get-started/configuration.md#traders) shows. Of the traders' folders, only the four starters' `trader.toml` and `Persona.md` are tracked by git, because the traders you create are your own data.

## Creating a trader

You create a trader while the gateway runs, without editing any file or restarting anything. You give it a name and a mandate, and optionally its models, its heartbeat and the times it is woken. The gateway then does three things in order.

1. It writes the trader's folder, its `trader.toml`, and a `Persona.md` written from the mandate and the schedule.
2. It starts the trader at once, alongside the others, and publishes a `trader_created` event so every open page shows it.
3. It sends the trader a first message asking it to restate its mandate, say what it would trade and how it would size and protect each trade, and propose a fuller `Persona.md` and, if the mandate calls for them, its own `[traders.<name>]` limits in TradingRules.md, through [proposals](your-files.md) you accept or reject.

!!! warning "A new trader may trade straight away"
    Until you add a `[traders.<name>]` table to TradingRules.md, a new trader has no limits of its own and trades within the account-wide limits, like any trader without an entry. Accept or edit its proposed limits before the market opens if you want it held to less.

A name uses lower-case letters, digits, hyphens and underscores, starts with a letter, and is at most 200 characters long, such as `banknifty-momentum`. The table below shows the four ways to create a trader.

| Where | How |
|---|---|
| The web page or the Android app | On the **Traders** page, press **New trader**, fill in the name and mandate, untick or tick models, optionally set a heartbeat and check times, and press **Create trader**. The page then opens the new trader's chat, so you see its introduction arrive |
| The terminal | `bin/trading-agent traders new banknifty-momentum --mandate "Intraday momentum in Bank Nifty options, buying only, flat by 15:15" --heartbeat 5 --checks 09:20,15:05`, with `--models claude,qwen` to choose the models; its first reply appears on the web page |
| Telegram | `/create banknifty-momentum Intraday momentum in Bank Nifty options, buying only, flat by 15:15`; the trader gets the default models and schedule, the chat switches to it, and its introduction arrives in that chat |
| The API | `POST /api/traders` with a JSON body holding `name`, `mandate` and optionally `backend_order`, `heartbeat_minutes`, `scheduled_checks` and `introduce`, as [The gateway API](../architecture/gateway-api.md#creating-retiring-and-restoring-traders) describes |

A heartbeat left out takes `[traders] heartbeat_minutes`, which is none on this machine, and a heartbeat of 0 means none.

## Retiring and restoring a trader

When a trader's mandate is finished or put aside, you retire it. A retired trader stops: it no longer answers messages, runs its schedule, or receives heartbeats, price alerts and fills. Its folder, memory, journal and conversations all stay, and `retired = true` is written to its `trader.toml`. Restoring it later starts it again with its memory and sessions.

Two rules protect the account. A trader that still owns an instrument or has an open order cannot be retired, because nobody would watch those positions afterwards, so flatten it first. The last running trader cannot be retired either. The table below shows where each action is done.

| Where | Retire | Restore |
|---|---|---|
| The web page or the Android app | **Retire** on the trader's card on the **Traders** page, after a confirmation | **Restore** under **Retired traders** on the same page |
| The terminal | `bin/trading-agent traders retire NAME` | `bin/trading-agent traders restore NAME` |
| Telegram | `/retire NAME` | `/restore NAME`, which also switches the chat to it |
| The API | `POST /api/traders/{trader}/retire` | `POST /api/traders/{trader}/restore` |

`bin/trading-agent traders list`, `/traders` in Telegram, and `GET /api/trader-records` list every trader, retired ones included, with its mandate. Against a gateway started from this version on a copy of this machine's workspace, the command printed the lines below on 31 October 2026, after a test trader was created and the scalper retired; mandates are cut short here.

```text
general (running): None of its own. This is the general trader, for trying trading-agent out, ...
  models: claude, deepseek, qwen, gemma; no heartbeat; checks: none
intraday (running): Intraday trades in liquid NSE stocks and index options (buying only), ...
  models: claude, deepseek, qwen, gemma; heartbeat every 10 min; checks: 09:05, 15:05, 15:35
positional (running): Swing and positional trades held for days to weeks, ...
  models: claude, deepseek, qwen, gemma; no heartbeat; checks: 08:45, 12:30, 15:40
scalper (retired): Very short trades of seconds to minutes in the most liquid instruments, ...
  models: claude_sonnet, deepseek, qwen, gemma; heartbeat every 2 min; checks: 09:10, 15:05
opening-range (running): Opening range breakouts in NIFTY 50 stocks, mis only.
  models: claude, deepseek, qwen, gemma; no heartbeat; checks: 09:30, 15:05
```

## What a trader is doing

Every trader is in one of the states below at any moment. The web page shows the state on the trader's card, in the trader menu, in the side panel and in the chat header, and `/status` reports it in the chat.

| State | What it means |
|---|---|
| idle | The trader is waiting for a message, an alert, a fill or a scheduled job, with its model processes ready |
| busy | The trader is running a turn; a new message steers that turn |
| waiting | The trader has a turn to run but waits for a free slot, because `[traders] maximum_running` traders are already running turns. Like a busy trader, it gets no heartbeats while it waits |
| sleeping | The trader has been idle for `[traders] sleep_after_minutes`, 30 minutes by default, and has stopped its model processes to save memory. Your next message, a price alert, a fill, a scheduled job or a heartbeat wakes it, and Claude resumes the same session, so the conversation carries on |
| stopped | The trader's loop is not running, such as while the gateway shuts down |

A trader with a heartbeat during market hours is never idle for long, so in practice traders sleep after the close and at weekends. Falling asleep publishes a `trader_sleeping` event.

## Moving from desks to traders

Traders were called desks until 31 October 2026. The first time any `trading-agent` command runs after that change, it moves the data an earlier version saved under the old names, after copying it to `workspace/.backups/desk-to-trader-<time>/`. The table below lists what it changes.

| Before | After |
|---|---|
| `workspace/desks/<name>/` | `workspace/traders/<name>/`, merged with the tracked `trader.toml` and `Persona.md` |
| `workspace/shared/desk_orders.db`, table `desk_orders`, column `desk` | `trader_orders.db`, table `trader_orders`, column `trader` |
| The `desk` column of the risk ledger's `ownership`, `approvals` and `day_owners` tables | `trader` |
| `"desk"` keys, values such as `"desk_started"` and `"flatten_desk"`, and `workspace/desks/` paths in the journals, sessions, cron jobs and Telegram pairings | The same with `trader` |
| `[desks.<name>]` tables in TradingRules.md | `[traders.<name>]` |
| The terminal program's remembered desk | Its remembered trader |

Free text, such as past conversations, notes and Memory.md, is left as it was written. Stop the service before updating, because the old gateway holds the old databases open.

## What every message starts with

Each message a trader receives starts with one line that tells it where it is in time: the India date and time, what woke it, and the market's state, such as "NSE closed today (weekend); next trading day Mon 19 Oct, holiday ahead: Tue 20 Oct Dussehra". Those facts change every turn, so they are in the message rather than in the instructions.

## Where each trader keeps its things

```text
workspace/traders/<trader>/
├── trader.toml       the record: mandate, models, schedule, retired or not
├── Persona.md        yours: style, holding period, products, cadence
├── Memory.md         the trader's lasting lessons
├── memory/  notes/   the trader's own files and daily notes
├── skills/agent/     the skills the trader wrote itself
├── sessions/         one conversation log per trading day
├── journal/          every event, one file per day
├── cron/             the trader's scheduled jobs and their runs
├── proposals/        changes it suggests to your files
└── scratch/          the one folder its bash sandbox may write
```

Each trader's own files are snapshotted before every change, in `workspace/.checkpoints/<trader>.git`, so any change can be undone on the Checkpoints page.
