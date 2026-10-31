# market_watcher.py

The market watcher (block 38): a loop with no model that wakes the traders when something happens.

## When it runs

Every 15 seconds while NSE equities or MCX trade (per `ExchangeHours` with the market calendar), and once a minute otherwise just to see whether the market has opened. A failing cycle is logged at an isolation point and the loop carries on.

## Fills

UBI's order book (`/api/orders/details`, an `orders` list) is read once per cycle, and only when a trader has an open, real order in the trader order book; dry-run orders reach no broker, so with none the book is not read at all. A broker order counts when its status is one of UBI's finished statuses (COMPLETE, CANCELLED, REJECTED, EXPIRED, taken from UBI's `order_book_filter.py`) and its `engine_parent_id` matches a record's `parent_id`, or its `order_id` the record's. Bracket exits share the bracket's parent id, so they are reported too. Each trader gets one message per cycle listing its updates, with `filled_quantity`, `average_price` and, when it did not complete, UBI's `status_message`.

Reported order ids are written to `workspace/shared/market_watcher.json` (the last 5,000), so a restart neither repeats a report nor drops one that finished while the gateway was down.

The watcher does not change the trader order book's state; flatten_trader already treats a finished order's "already finished" answer as done.

## Alerts

Each alert's instrument price is read once per cycle (several alerts on one instrument share it). A crossed alert is removed and its trader woken with the price and the note.

## Account and loss limits

Once a minute it calls `RiskEngine.check_account`. Before this milestone the loss limits were checked only when an order was evaluated, so a losing position held without new orders would never have fired the kill switch.

## Verified on 2026-10-17 (a Saturday)

Cycles do not run on a weekend, so the checks were called once from a script against the real UBI: the account read gave a balance of 23,723.06 with no positions; with no real orders the order book was not read; an alert planted below IDEA's real price (12.59) fired, reached the trader and was removed. Fills could not be seen live, because there were no real orders; they are covered by the tests.

## account_status (milestone 16)

After each account check the watcher publishes `account_status` (no trader): total balance, day P&L, each trader's P&L and the open position count, once a minute while the market is open. The web interface will show it.

## Fill events name the stock (milestone 19)

The fill event now carries the order's symbol, side and quantity, so a phone notification can say what filled without looking anything up.
