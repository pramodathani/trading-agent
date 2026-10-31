# account_routes.py

The account routes read UBI through the same snapshot reader the risk engine uses, so the web page shows the numbers the risk engine judged by. When UBI cannot be read the answer is 503, not an error page, so the frontend can show "UBI unavailable" and keep working.

`/api/trader-orders` is the trader order book (which trader placed which order), separate from UBI's own order list, because UBI does not know about traders beyond the tag.

The kill switch needs the word FLATTEN in the body. A button press alone could be a mis-click, and the switch halts every trader until the next day. It calls the same `KillSwitch.trigger` the loss limit uses, so in dry_run mode the flatten is a dry run. The halt lasts until tomorrow, matching the daily loss limit's halt. The live test did not fire it, because a real halt would stop every trader until the next day; the tests cover it with a stand-in.

## Symbols and per-position profit (milestone 18)

The ledger stores only UBI's instrument ids, which are long UUIDs that mean nothing on a web page. The account answer therefore gives each owner a symbol, taken from the open positions or else from the trader's open orders, and falls back to the id only when neither knows it. Each position also carries its own day profit or loss from the snapshot, so the Trading page can show it per row.

## Live trader names

The names are kept as given, not copied, and the gateway passes its live dictionary of traders, so a trader created after start-up appears here at once.
