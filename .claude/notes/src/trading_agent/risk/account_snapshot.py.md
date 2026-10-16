# account_snapshot.py

Three reads per order: funds (`summary.total_balance`, `summary.margin_utilized`), positions (`net` rows and `summary.day.total_pnl`) and holdings. The field names come from UBI's docs and from tradingmachine's `net_positions`, which documents the position rows; on 2026-10-17 the account had no positions, so the row format could not be seen live. Holdings are read so the user's own shares are protected, by id and, because one holding row had no id, by symbol.
