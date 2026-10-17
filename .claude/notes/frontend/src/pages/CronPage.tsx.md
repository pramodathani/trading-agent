# CronPage.tsx

The page is named Schedule in the sidebar, since "cron" means nothing to someone who has not used Unix. Built-in jobs (heartbeat, rollover, scheduled checks) can be run now but not deleted, because they come from trading_agent.toml. The next runs come from the scheduler itself; on 2026-10-17 every job's list skipped Tuesday 20 October, the Dussehra holiday.

The form creates repeating jobs only. One-off jobs are created by the desks with schedule_wakeup, which is the common case for them.
