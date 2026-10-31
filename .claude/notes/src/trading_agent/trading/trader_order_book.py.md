# trader_order_book.py

The trader order book is a separate SQLite file, `workspace/shared/trader_orders.db`, rather than another table in the risk ledger, because the risk ledger is written only by the risk engine and the kill switch, while this record is written by the order tools. It is ignored by git like the ledger.

`find` always filters by trader, so one trader can never find, change or cancel another trader's order.

`now_text` is a static method because it needs no state of the book; it keeps the time format of `placed_at` in one place.
