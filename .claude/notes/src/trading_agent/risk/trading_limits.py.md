# trading_limits.py

The limits live in the user's own TradingRules.md, in a fenced ```toml limits block, so that the rules a person reads and the limits the code enforces are the same text. The file is read before every order, so an accepted proposal takes effect on the next one. Every field has a range check; an invalid block refuses every new position, and the doctor reports it.
