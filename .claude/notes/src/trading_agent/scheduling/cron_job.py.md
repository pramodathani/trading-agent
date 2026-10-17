# cron_job.py

A job is either repeating (five cron fields in India time, through `croniter`) or one-off (`run_at`). `trading_days_only` (default on) skips weekends and holidays from the market calendar; `market_hours_only` keeps only times when NSE equities are open according to `ExchangeHours`, which handles the 09:15 start that cron fields cannot express. Candidates are searched up to 2,000 steps, enough for a five-minute heartbeat across a long holiday weekend.

`catch_up` decides whether a run missed while the gateway was down is made up after a restart: on for user and desk jobs and the rollover, off for the heartbeat, where an old heartbeat has no value.

Jobs are frozen dataclasses checked in `__post_init__`, so an invalid job can never be stored or run; an invalid entry in jobs.json is skipped with a warning.
