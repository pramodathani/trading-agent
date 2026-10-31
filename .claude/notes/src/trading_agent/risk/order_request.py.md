# order_request.py

The order tools of milestone 10 build one of these from what the model asks for, after looking the instrument up, so the engine never sees a half-described order. The quantity is in units (lots times lot size for derivatives), always positive, with the side in `transaction_type`.

`after_market` defaults to False so the requests built by `flatten_trader` and the bracket tool, which are never after-market, need no change. `describe()` adds ", after market" so the journal, the events and the tool's answer show it.
