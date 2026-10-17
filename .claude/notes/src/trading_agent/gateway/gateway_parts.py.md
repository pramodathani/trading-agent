# gateway_parts.py

The API needs to reach many objects the desk builder creates: each desk's session store, cron store, alerts, skills, checkpoints and tools, and the shared risk engine, ledger, kill switch, order book, proposals and so on. Passing them one by one to each route group would make the application's wiring long and fragile, so the builder collects them into two plain dataclasses as it builds the desks.

`DeskParts` is per desk and `SharedParts` is shared. Each route group takes the whole bundle but uses only the fields it needs, which is why the tests can fill unused fields with `None`: a dataclass does not check types at run time.

Milestone 17 introduced both.
