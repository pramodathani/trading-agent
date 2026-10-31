# trade_journal.py

The journal is the audit trail: every event of every trader, as one JSON line, in a file per trader per India date, only ever appended. It subscribes when it is built, before the gateway starts the traders, so the traders' first events are not missed, and with a queue of 100,000 events instead of the usual 1,000, because unlike a browser tab it must not lose events; if it ever does, the count is logged as an error.

Streamed text pieces are skipped because the final `text` event holds the whole reply; everything else, including tool calls with their arguments and results, rate limits and backend switches, is kept.

Dates are India dates, so a trading day's events share one file. The journals are out of git: they are written continuously by the agent, and git is for files people edit. A backup command is in the plan's backlog.
