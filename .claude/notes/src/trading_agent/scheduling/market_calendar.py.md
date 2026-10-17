# market_calendar.py

The market calendar (milestone 15) reads UBI's own exchange calendar files instead of keeping a second holiday list. UBI's files are one YAML per year, generated from the exchanges' publications (NSE holiday master, BSE, MCX, the NCDEX circular), and are what UBI's order engine uses for scheduled orders. Reading the same files means trading-agent and UBI can never disagree about a holiday. The folder is `market_calendar_directory` in trading_agent.toml; the bash sandbox hides the UBI project, but the gateway reads it directly.

## Contents

- Holidays per exchange and calendar (`equity`, `currency`, `commodity`), with `closed` = `all`, or `morning`/`evening` for commodity calendars split at 17:00.
- Special sessions, such as Muhurat trading, per exchange and calendar, with their hours; a special session makes a day a trading day even when it is a weekend or listed as a holiday.
- `calendar_for` maps an instrument's exchange and segment to its calendar.

## Failure

A missing folder or a damaged file is logged, and the calendar then knows weekends only; the doctor warns, because holidays would then look like trading days to the risk engine and the scheduler. A new year's file must be added to UBI each December; the doctor warns when the current year is missing.

## What it changed

Tuesday 2026-10-20 is Dussehra. Before this milestone the risk engine would have allowed new orders that day; now it refuses them with "it is an exchange holiday (Dussehra)".
