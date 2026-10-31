# trading_limits.py

The limits live in the user's own TradingRules.md, in a fenced ```toml limits block, so that the rules a person reads and the limits the code enforces are the same text. The file is read before every order, so an accepted proposal takes effect on the next one. Every field has a range check; an invalid block refuses every new position, and the doctor reports it.

## Trader daily loss limit (milestone 16)

`[traders.<name>] daily_loss_limit_percent`, a share of the live total balance, like the account limits. It is optional and left out of the user's TradingRules.md, because the size of each trader's loss limit is the user's decision.
