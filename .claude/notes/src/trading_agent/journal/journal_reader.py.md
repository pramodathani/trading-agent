# journal_reader.py

`JournalReader` reads one India date's events from a journal folder. It was taken out of `memory_routes.py` on 2026-10-18 so that `/subagents`, and later `/review`, read the journal the same way the gateway's `GET /api/desks/{desk}/journal` does, without a second copy of the parsing.

The file for a date is named by the India date, because `TradeJournal.path_for` names files that way. `today()` therefore uses the India date too; between midnight in India and 05:30 the UTC date is still the day before.

Lines that are not JSON are skipped rather than raising, because a line cut short by a crash mid-write must not hide the rest of the day.

The clock is injectable so tests can fix "today".
