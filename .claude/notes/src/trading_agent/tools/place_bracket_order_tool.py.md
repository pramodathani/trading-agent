# place_bracket_order_tool.py

The bracket is sent with tradingmachine's `BracketOrder`, which builds UBI's `synthetic` object. UBI's engine works the exits in real time, which is how the scalper desk can be protected even though one model decision takes seconds.

The side checks (a buy's stop below the entry and target above it, and the stop's limit on the far side of its trigger) run before the risk engine is asked, so a mistaken bracket costs no UBI call. For a market entry the last price stands in for the entry price. Only the entry is checked by the risk engine, because the exits only reduce the position.

The entry's `order_type` is limited to market and limit; stop entries are left for later.
