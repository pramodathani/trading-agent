# roster_routes.py

Ported from research-agent's roster routes (commit `6d68744`), with the name limit of 200 characters from `ec5c790`.

The records have their own address, `/api/trader-records`, because `/api/traders/records` would be read as the trader named "records" by the existing trader routes. Creation answers 201 with the record; every refusal from the trader store (a bad or taken name, an unknown backend, a check time that is not HH:MM, retiring the last trader or one that still holds positions) becomes a 400 whose detail is the store's own sentence, so the web page, the command line and Telegram can show it unchanged.

The request carries the mandate, the backend order, the heartbeat and the scheduled checks, because the user chose a creation form that asks for the schedule as well as the name and mandate. `heartbeat_minutes` is `null` for the default and `0` for none.

Checked on 31 October 2026 against a gateway started from the worktree on a copy of the migrated live workspace: the four starter traders were listed with their schedules, and a trader with a 160-character name was created, appeared at once in `/api/traders` and `/api/usage`, and was retired and restored.
