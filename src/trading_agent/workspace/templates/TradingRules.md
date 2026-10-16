# TradingRules.md: strategies and hard limits

Status: template, not filled in yet.

The limits block below is read by the risk engine, which is plain code, not an AI model. It refuses any order that breaks these limits, whichever desk or model sends it. Until the user fills this file in, trading is switched off.

```toml limits
[account]
trading_enabled = false
daily_loss_limit_rupees = 0
maximum_order_value_rupees = 0
maximum_open_positions = 0
trading_window = "09:20-15:15"

[desks.main]
capital_rupees = 0
daily_loss_limit_rupees = 0
maximum_order_value_rupees = 0
maximum_open_positions = 0
allowed_products = []
allowed_instruments = []
maximum_orders_per_minute = 0
```

## Strategies

Describe each strategy in plain words: what to look for, when to enter, where the stop goes, where to take profit, and when not to trade at all.
