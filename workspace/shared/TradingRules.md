# TradingRules.md: strategies and hard limits

The limits block below is read by the risk engine, which is plain code, not an AI model. It refuses any order that breaks these limits, whichever trader or model sends it.

## How the limits work

- Every percentage is a share of the total account balance across all brokers. The risk engine reads that balance live from UBI each morning and before each order, so the rupee amounts grow and shrink with the account.
- `capital_percent` is how much of the balance the agent may use in total. A trader's optional `capital_share_percent` reserves it a share of that capital; when shares are set, they should add up to 100 or less. A trader without one draws on the shared pool, limited only by the account-wide limits.
- `daily_loss_limit_percent` stops every trader for the rest of the day once the day's losses reach it, and closes every position.
- `weekly_loss_limit_percent` stops every trader until the next Monday once the week's losses reach it.
- `maximum_order_value_percent` caps the margin any single order blocks: the full cost for delivery buys and option buys, and the estimated margin for intraday orders, futures and sold options.
- `maximum_open_positions` caps the number of open positions. Leave it out for no cap.
- `trading_window` is when new orders are allowed. `"exchange_hours"` means each exchange's own opening and closing times (NSE and BSE, MCX, currency), taken from the market calendar, which also follows MCX's change of closing time with US daylight saving. A range such as `"09:20-15:15"`, in India time, applies the same window to every exchange instead.
- `allow_option_writing` lets traders sell options to open or enlarge a short position. While it is false, only buying options, and selling options already held, is allowed.
- A trader's optional `maximum_orders_per_minute` caps how fast it may send orders. Leave it out for no cap.
- A trader's `allowed_products` and `allowed_instruments` restrict what it may trade. An empty list means everything is allowed.
- A trader's optional `daily_loss_limit_percent` stops only that trader for the rest of the day once its own losses reach that share of the total balance; the other traders keep trading. A trader's losses are those of the instruments it held that day, closed trades included. Leave it out for no trader limit; the account-wide limits still apply.

```toml limits
[account]
trading_enabled = true
capital_percent = 100
daily_loss_limit_percent = 15
weekly_loss_limit_percent = 35
maximum_order_value_percent = 25
trading_window = "exchange_hours"
allow_option_writing = false

[traders.general]
allowed_products = []
allowed_instruments = []

[traders.intraday]
allowed_products = ["mis"]

[traders.scalper]
allowed_products = ["mis"]
daily_loss_limit_percent = 3

[traders.positional]
allowed_products = ["cnc", "nrml"]
```

## Order types each trader may use

Not yet enforced by the risk engine: today the traders can place only plain orders (market, limit, sl, sl-m) and brackets. This list applies once trading-agent exposes UBI's synthetic order types as tools; until the risk engine reads an `allowed_order_types` key, the traders follow it themselves. Plain orders are allowed to every trader. Names are UBI's type names.

- Every trader, never: `square_off` and `close_on_trigger` (they act on a whole instrument or product across the shared account and could close or cancel another trader's positions; use flatten_trader instead).
- While `allow_option_writing` is false, never on options: `stop_and_reverse`, `two_sided_breakout`, `grid`, `two_sided_quote`, `scale_with_profit_taker` and a `legged_spread` or `oto` whose sell leg would open a short option. On futures and stocks they follow the trader lists below.

- scalper (intraday, seconds to minutes):
  - Entry with exits: `bracket`, `cover`, `scale_out`, `oto`, `time_stop`, `two_sided_breakout` (futures and stocks only).
  - Protection: `oco`, `trailing_stop`, `atr_trail`, `stepped_stop`, `candle_close_stop`, `hidden_stop` (only with a backstop).
  - Conditional entry: `market_if_touched`, `limit_if_touched`, `cross_instrument`, `indicator_triggered`.
  - Execution: `marketable_limit`, `chaser`, `peg`, `post_only`, `good_till_time`, `freeze_slicer`.
- intraday: everything the scalper may use, plus `scheduled`, `discretionary`, `iceberg`, `twap`, `vwap`, `ladder`, `basket`, `oca`, `strategy_stop`, `underlying_peg`, `volatility`.
- positional (multi-day): `bracket`, `cover`, `scale_out`, `oco`, `oto`, `trailing_stop`, `atr_trail`, `stepped_stop`, `gtt`, `daily_stop`, `limit_if_touched`, `market_if_touched`, `cross_instrument`, `scheduled`, `opening_auction`, `closing_price`, `iceberg`, `twap`, `vwap`, `implementation_shortfall`, `participation`, `liquidity_seeking`, `accumulation`, `ladder`, `basket`, `oca`, `legged_spread`, `strategy_stop`, `attached_hedge`, `exposure_hedge`, `freeze_slicer`.
- general: every type, subject to the two "never" rules above.

## Strategies

Standing rule: options are bought only. No option writing without Pramod's explicit permission.

### Scalper trader

Both setups read signals on the NIFTY index and trade NIFTY options, bought only, `mis`, entered with `place_bracket_order` (stop and target set before entry). All candles are 5-minute candles of the NIFTY index.

**Common rules**
- Contract: the nearest NIFTY weekly expiry; on its expiry day, the next weekly expiry. Strike: the at-the-money strike (nearest 50) when the signal fires; a call for an upward signal, a put for a downward one.
- Liquidity filter: skip the trade if the option's bid-offer spread is wider than 1% of its premium, or the best bid or offer is thinner than 5 lots.
- Entry: a limit at the best offer plus 2 ticks, so it fills at once or not at all; cancel it if unfilled after 30 seconds.
- Sizing: risk per trade = 1% of the total balance, where risk = (entry premium − stop) × quantity. Quantity = that risk ÷ (stop distance × lot size), rounded down to whole lots. If even 1 lot risks more than 1.5%, skip the trade.
- New entries only 09:30–11:00 and 13:30–14:45. Be flat by 15:05 (flatten_trader).
- At most two positions open at once, and never two in the same direction.
- Stop for the day after three losing trades in a row, or when the trader's daily loss limit (3%) is reached.
- Skip the first 30 minutes after a scheduled market-moving event (RBI policy, Union Budget, US Fed decision the night before counts for the open).

**Setup A: opening-range breakout (09:30–11:00)**
1. Opening range = high and low of the NIFTY index from 09:15 to 09:30 (first three candles).
2. Skip the day for this setup if the range is narrower than 0.15% or wider than 0.70% of the index.
3. Signal: a candle closes above the range high (buy call) or below the range low (buy put).
4. Bracket on the option: stop 15% below entry premium, target 25% above it.
5. Manual exits (at the next check): if the index closes a candle back inside the opening range, close the trade; if the target has not been hit 20 minutes after entry, close it.
6. At most one trade per direction per day.

**Setup B: momentum candle (09:30–11:00 and 13:30–14:45)**
1. Signal: a candle whose body is at least 0.20% of the index and which closes in the top 20% of its range (buy call) or the bottom 20% (buy put).
2. Only in the direction of the day's trend: index above its opening-range high for calls, below its opening-range low for puts.
3. Bracket on the option: stop 10% below entry premium, target 15% above it.
4. Manual exit: if the target has not been hit 15 minutes after entry, close the trade.
5. At most two trades of this setup per day.

**Review:** after 10 trading days in dry_run, the trader reports win rate, average win and loss, and slippage per setup, and proposes changes to these numbers. When trailing stops, time stops and index-triggered exits become available as tools, the manual exits above move into the order itself.

Other traders: no strategy written yet; they must not open positions.
