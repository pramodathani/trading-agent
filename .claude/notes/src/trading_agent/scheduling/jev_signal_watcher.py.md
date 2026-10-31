# jev_signal_watcher.py

The Jev signal watcher: a loop with no language model that asks Jev every 30 seconds and wakes the Jev traders only on a confident buy or sell.

## Why it exists

The user asked for the jev-scalper to check the market every 30 seconds. A 30-second heartbeat would have been about 750 Claude turns a trading day on the shared Max subscription, and the cron scheduler works in whole minutes. On 2026-11-01 the user chose to give the frequent checks to Jev instead, which answers in under a second for a tiny fraction of a model turn's cost, and to keep a 2-minute heartbeat for managing open positions.

## Why it is separate from the market watcher

The market watcher's cycle is 15 seconds and its job is facts (fills, alerts, the account). Jev's cycle is 30 seconds and its job is an opinion. Keeping them apart means a slow or failing Jev request can never delay a fill report or the loss-limit check, and the watcher only exists when the TypeSafe key is set.

## Rules

- It asks Jev once per cycle however many Jev traders there are, and not at all when none is running.
- It only runs inside `signal_window` (09:30 to 14:45 by default, the jev-scalper's entry window) on NSE trading days, so it never wakes a trader for an entry it may not make.
- A trader that is busy, waiting for a turn slot, has triggers queued, is paused or is stopped is not woken. Paused traders answer every trigger with a paused reply, so waking them would fill the chat. Such a trader is offered the signal on the next cycle.
- The same signal wakes a trader at most once every `repeat_after_minutes`. A hold, a weak signal or a failure forgets the last signal, so buy, hold, buy wakes the trader twice; this is deliberate, because the market changed in between.
- Wake-ups use the market watcher's trigger source, so the web page and Telegram treat them like the other watcher messages; the heading says they come from Jev.
