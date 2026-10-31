# place_order_tool.py

The lot-size check runs before the risk engine, because UBI does not check lots itself and a wrong quantity is the commonest model mistake with futures and options. A plain limit order is held inside UBI's engine as a `virtual_limit` until the market reaches its price, and a plain market order runs as a `marketable_limit` for up to 30 seconds; both are UBI's defaults and are described to the model rather than overridden.

## After-market orders

`PlaceOrderArguments` adds `after_market` to `OrderArguments` here rather than in `order_arguments.py`, because only a plain order can be one: the bracket order tool also builds on `OrderArguments`, and UBI's bracket is worked live by its engine, which an order queued at the broker until the open cannot be. tradingmachine's `place_order` already took `after_market`; UBI then sends the order straight to the broker as its after-market variety (Zerodha's `amo`, Dhan's `afterMarketOrder` with `amoTime` `OPEN`) instead of holding a limit order as a `virtual_limit`. `ioc` is refused with it, because an after-market order waits for the open. A dry-run after-market limit order for 1 KWIL, sent on Saturday 2026-10-31, came back from UBI with the Dhan request it would have sent, which showed that UBI's instrument list was loaded at a weekend and that the order would have gone to Dhan.
