# Scheduling and watching

An agent that only answers messages is not always on. Two parts of the gateway wake the desks by themselves: the **cron scheduler**, which runs on the clock, and the **market watcher**, which runs on what the market does.

## The cron scheduler

Every desk has built-in jobs from `trading_agent.toml` and its own jobs from `cron/jobs.toml`. Times are in India time, and a job marked "trading days only" skips weekends and exchange holidays, read from UBI's calendars.

| Job | Set by | What it does |
|---|---|---|
| Heartbeat | `heartbeat_minutes` | While NSE equities trade, wakes the desk to look at its positions, orders, alerts and plans; it answers `NOTHING_TO_DO` silently when nothing needs doing |
| Scheduled checks | `scheduled_checks` | Wakes the desk at set times to do what its Persona.md says for that time |
| Rollover | `rollover_time` | Summarises the day and starts a fresh session |
| The desk's own jobs | `cron_create`, `schedule_wakeup`, or the Schedule page | An instruction to the desk, a shell command run in the sandbox without a model, or a task for a subagent |

<figure class="diagram">
--8<-- "docs/assets/diagrams/scheduler.svg"
<figcaption>The scheduler times every desk's jobs against the market calendar. The orange dots wake the desk, run a command job or start a subagent job; the blue dots are results.</figcaption>
</figure>

A run missed while the gateway was down is made up once after it starts again, and every run is recorded and shown on the Schedule page.

## The market watcher

The watcher is a loop with no model. Every fifteen seconds while NSE equities or MCX trade, it reads UBI's order book for finished orders, checks the desks' price alerts against last prices, and once a minute reads the account's profit and loss, even when nobody trades.

<figure class="diagram">
--8<-- "docs/assets/diagrams/market-watcher.svg"
<figcaption>Orange dots are market data read from UBI, and the loss-limit check reaching the kill switch; blue dots are the desk being woken with a fill, an alert or a webhook message.</figcaption>
</figure>

| It sees | It does |
|---|---|
| A desk's order finished at the broker | Wakes that desk once with the fill, rejection or cancellation |
| A price alert crossed | Wakes the desk once, then removes the alert |
| The account at its daily or weekly loss limit | Fires the kill switch |
| A desk at its own loss limit | Halts that desk for the day |

## Webhooks

`POST /hooks/wake/<desk>` lets TradingView alerts or your own scripts wake a desk with a message. The body is the message, as plain text or as JSON with a `text` or `message` field. The webhook's own token goes in a `token` query parameter, because TradingView cannot set headers, or in an `X-Webhook-Token` header. It is a separate token from the gateway's, so pasting it into another service never exposes the token that controls the gateway. Without `TRADING_AGENT_WEBHOOK_TOKEN` in `.env`, the route answers 404 as if it did not exist.

```bash
curl -X POST "http://127.0.0.1:8120/hooks/wake/intraday?token=$WEBHOOK_TOKEN" \
     -d "NIFTY broke above its opening range"
```
