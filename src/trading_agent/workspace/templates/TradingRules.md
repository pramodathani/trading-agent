# TradingRules.md: strategies and hard limits

Status: template, not filled in yet.

The limits block below is read by the risk engine, which is plain code, not an AI model. It refuses any order that breaks these limits, whichever desk or model sends it. Until the user fills this file in, trading is switched off.

## How the limits work

- Every percentage is a share of the total account balance across all brokers. The risk engine reads that balance live from UBI each morning and before each order, so the rupee amounts grow and shrink with the account.
- `capital_percent` is how much of the balance the agent may use in total. A desk's optional `capital_share_percent` reserves it a share of that capital; when shares are set, they should add up to 100 or less. A desk without one draws on the shared pool, limited only by the account-wide limits.
- `daily_loss_limit_percent` stops every desk for the rest of the day once the day's losses reach it, and closes every position.
- `weekly_loss_limit_percent` stops every desk until the next Monday once the week's losses reach it.
- `maximum_order_value_percent` caps the margin any single order blocks: the full cost for delivery buys and option buys, and the estimated margin for intraday orders, futures and sold options.
- `maximum_open_positions` caps the number of open positions. Leave it out for no cap.
- `trading_window` is when new orders are allowed. `"exchange_hours"` means each exchange's own opening and closing times (NSE and BSE, MCX, currency), taken from the market calendar, which also follows MCX's change of closing time with US daylight saving. A range such as `"09:20-15:15"`, in India time, applies the same window to every exchange instead.
- `allow_option_writing` lets desks sell options to open or enlarge a short position. While it is false, only buying options, and selling options already held, is allowed.
- A desk's optional `maximum_orders_per_minute` caps how fast it may send orders. Leave it out for no cap.
- A desk's `allowed_products` and `allowed_instruments` restrict what it may trade. An empty list means everything is allowed.

```toml limits
[account]
trading_enabled = false
capital_percent = 0
daily_loss_limit_percent = 0
weekly_loss_limit_percent = 0
maximum_order_value_percent = 0
trading_window = "exchange_hours"
allow_option_writing = false

[desks.main]
allowed_products = []
allowed_instruments = []
```

## Strategies

Describe each strategy in plain words: what to look for, when to enter, where the stop goes, where to take profit, and when not to trade at all.
