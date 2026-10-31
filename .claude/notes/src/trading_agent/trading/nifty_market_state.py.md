# nifty_market_state.py

Builds the market state Jev is shown: the NIFTY index's quote headline fields and its latest 5-minute candles.

## Why code builds the state

If the trader's language model wrote the state, Jev would be judging the model's summary, and two calls a minute apart could describe the same market differently. Built in code, every Jev call sees the same kind of facts, which also makes Jev's answers comparable in the ten-day review.

## What is included

- `last_price`, `ohlc`, `previous_close` and `change_percent` from tradingmachine's unified quote. Depth and the other fields are left out, because an index has no order book and every extra field costs input tokens.
- The last `candle_count` 5-minute candles (24 by default, two hours), from the last three days so the first candles of the morning still have yesterday's afternoon before them. Only `datetime`, `open`, `high`, `low`, `close` and `volume` are kept; tradingmachine also returns `exchange`, `segment`, `interval` and `oi`. The datetime is turned into a string before `to_json`, so it keeps its India offset instead of being converted to UTC.

## Unverified

`get_candles` warns that the latest day's candle may not be stored until after the close. That note is about daily candles, but it has not been checked whether today's 5-minute candles are available during the session. It was a Sunday when this was written, so the check waits for the next trading day; if they are missing, Jev sees only the quote and the earlier days' candles.

The index is named as exchange `nse`, segment `equity_indices`, symbol `NIFTY`, following `InstrumentArguments`; this too is first exercised live on the next trading day.
