# The risk engine

No person approves the desks' orders. The risk engine is the only gate between a desk and the market, so its limits are written in code, read from your TradingRules.md, and cannot be changed by any model. It runs before every order from every desk, and refuses with every reason it found, which the desk reads and can act on.

<figure class="diagram">
--8<-- "docs/assets/diagrams/risk-checks.svg"
<figcaption>The six questions the risk engine asks of every order, in order. The blue dots are answers read from TradingRules.md, from UBI and from the risk ledger.</figcaption>
</figure>

## The limits

The limits are a fenced block in `workspace/shared/TradingRules.md` tagged `toml limits`. This is the block on this machine today:

```toml
[account]
trading_enabled = true
capital_percent = 100
daily_loss_limit_percent = 15
weekly_loss_limit_percent = 35
maximum_order_value_percent = 25
trading_window = "exchange_hours"
allow_option_writing = false

[desks.main]
allowed_products = []
allowed_instruments = []

[desks.intraday]
allowed_products = ["mis"]

[desks.scalper]
allowed_products = ["mis"]

[desks.positional]
allowed_products = ["cnc", "nrml"]
```

### Account limits

| Setting | Meaning |
|---|---|
| `trading_enabled` | Whether any desk may open or enlarge a position |
| `capital_percent` | The share of the total balance the agent may commit as margin |
| `daily_loss_limit_percent` | Today's loss, as a share of the live balance, that stops every desk and closes every position |
| `weekly_loss_limit_percent` | This week's loss that stops every desk until Monday |
| `maximum_order_value_percent` | The largest margin one order may block |
| `maximum_open_positions` | The most instruments held at once, or no cap |
| `trading_window` | `"exchange_hours"` for each exchange's own session, or `"HH:MM-HH:MM"` in India time |
| `allow_option_writing` | Whether a desk may sell options to open or enlarge a short position |

### Desk limits

| Setting | Meaning |
|---|---|
| `capital_share_percent` | The desk's share of the agent's capital, or the shared pool |
| `allowed_products` | The products the desk may use; empty allows all |
| `allowed_instruments` | The symbols the desk may trade; empty allows all |
| `maximum_orders_per_minute` | How many orders the desk may send in a minute |
| `daily_loss_limit_percent` | Today's loss on the stocks this desk owned that stops this desk alone |

On 17 October 2026 you chose to set no desk loss limits, so only the account's 15% daily and 35% weekly limits apply.

## One stock, one desk

The desks share one account, so two desks trading the same stock would tangle their positions. The risk ledger records which desk owns each stock: a desk claims it with its first order, and releases it when it is flat. Another desk's order in that stock is refused with "INFY belongs to the intraday desk; one desk trades an instrument at a time." A claim on a stock the desk ordered but never bought lapses after `risk.ownership_grace_minutes`, 30 by default.

<figure class="diagram">
--8<-- "docs/assets/diagrams/desks.svg"
<figcaption>Orange dots are orders from the four desks reaching the one risk engine; the blue dot is the scalper being refused a stock the intraday desk holds.</figcaption>
</figure>

## Two principles

**When in doubt, no.** If the limits cannot be read from TradingRules.md, or the account cannot be read from UBI, every new position is refused. That is why the Files page will not save a TradingRules.md whose limits cannot be read.

**Getting out is never blocked.** Every limit applies to opening or enlarging a position. An order that only reduces or closes the desk's own position is always allowed, even when the desk or the account is halted, because a limit that stopped you leaving would make the loss worse.

## The kill switch

At the account's daily loss limit, the market watcher fires the kill switch: every desk is halted until the next day and UBI is asked to flatten the whole account. In `dry_run` mode the flatten is a dry run. You can fire it yourself on the Trading page, by typing FLATTEN, or on Telegram with `/kill CONFIRM <reason>`.

A desk reaching its own daily loss limit stops only that desk, for the rest of the day.
