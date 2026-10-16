# TradingRules.md: strategies and hard limits

Status: template, not filled in yet.

The limits block below is read by the risk engine, which is plain code, not an AI model. It refuses any order that breaks these limits, whichever desk or model sends it. Until the user fills this file in, trading is switched off.

## How the limits work

- Every percentage is a share of the total account balance across all brokers. The risk engine reads that balance live from UBI each morning and before each order, so the rupee amounts grow and shrink with the account.
- `capital_percent` is how much of the balance the agent may use in total. Each desk's `capital_share_percent` is its share of that capital, and the desks' shares should add up to 100 or less.
- `daily_loss_limit_percent` stops every desk for the rest of the day once the day's losses reach it, and closes every position.
- `weekly_loss_limit_percent` stops every desk until the next Monday once the week's losses reach it.
- `maximum_order_value_percent` caps the value of any single order.
- `maximum_open_positions` caps the number of open positions. Leave it out for no cap.
- `trading_window` is the part of the day, in India time, when new orders are allowed.

```toml limits
[account]
trading_enabled = false
capital_percent = 0
daily_loss_limit_percent = 0
weekly_loss_limit_percent = 0
maximum_order_value_percent = 0
trading_window = "09:20-15:15"

[desks.main]
capital_share_percent = 100
allowed_products = []
allowed_instruments = []
maximum_orders_per_minute = 0
```

## Strategies

Describe each strategy in plain words: what to look for, when to enter, where the stop goes, where to take profit, and when not to trade at all.
