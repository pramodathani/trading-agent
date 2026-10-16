# risk_ledger.py

SQLite from the standard library, in `workspace/shared/risk_ledger.db`, so ownership, approvals, daily profit and loss and halts survive a restart; it is out of git. It is shared by every desk because the limits are account-wide. One connection with a lock serves every caller; the engine's writes are tiny and rare, so this is far from a bottleneck. Times are stored as ISO text in India time, which sorts correctly.

A halt lasts until `until_date`: the next day for the daily limit, the next Monday for the weekly one.
