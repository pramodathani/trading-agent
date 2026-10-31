# risk_ledger.py

SQLite from the standard library, in `workspace/shared/risk_ledger.db`, so ownership, approvals, daily profit and loss and halts survive a restart; it is out of git. It is shared by every trader because the limits are account-wide. One connection with a lock serves every caller; the engine's writes are tiny and rare, so this is far from a bottleneck. Times are stored as ISO text in India time, which sorts correctly.

A halt lasts until `until_date`: the next day for the daily limit, the next Monday for the weekly one.

## day_owners (milestone 16)

`claim` also records which trader owned the instrument that day, in `day_owners`. Ownership itself is released when the trader is flat, so without this record a loss realised on a closed trade could not be put down to the trader that made it. The last trader to claim an instrument that day gets it.

## Owners and halts for the API (milestone 17)

`owners` lists every stock a trader owns now, and `halts_in_force` lists the halts that still apply today, for the Trading page.

`release` deletes a claim only when it belongs to the named trader, so a trader can never give away another trader's instrument. `day_owners` is left alone, because it records who owned the instrument that day for each trader's day profit and loss.
