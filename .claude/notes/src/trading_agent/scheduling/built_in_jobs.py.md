# built_in_jobs.py

The heartbeat and the after-close rollover come from the trader's settings in trading_agent.toml (`heartbeat_minutes`, `rollover_time`), not from jobs.json, so the trader cannot delete them; `cron_list` shows them.

- **Heartbeat**: off by default, because every heartbeat is a model turn (on Claude, part of the Max subscription's limits). When on, it runs every N minutes during NSE equity hours on trading days, and the trader may answer `NOTHING_TO_DO`.
- **Rollover**: `/rollover` at 15:45 India time on trading days, so the day's summary and skill review run right after the close. The session keeper's lazy rollover on the first turn of a new date still exists as a fallback.

## Scheduled checks (milestone 16)

A trader's `scheduled_checks` times become built-in jobs `check-HHMM` on trading days, telling the trader to do what its Persona.md says for that time; it may answer NOTHING_TO_DO. They do not catch up after a restart, because a missed 09:05 plan is no use at 13:00. cron_delete refuses them like the other built-ins.
