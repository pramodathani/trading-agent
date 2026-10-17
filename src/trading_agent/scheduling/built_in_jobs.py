"""The two jobs every desk gets from trading_agent.toml rather than from its jobs file.

- The heartbeat wakes the desk every few minutes while NSE equities trade, to look at its positions, orders and plans. It is off unless the desk's heartbeat_minutes is set, because every heartbeat is a model turn. A heartbeat the desk answers with NOTHING_TO_DO produces no message.
- The rollover runs /rollover after the close on trading days, 15:45 by default, so the day's summary and the skill review happen right after the market shuts instead of with the next morning's first message.

Typical usage example:

  jobs = BuiltInJobs().jobs(heartbeat_minutes=15, rollover_time='15:45')
"""

from trading_agent.scheduling import cron_job as cron_job_module

HEARTBEAT_TEXT = '[Heartbeat] Look at your open positions, orders, price alerts and plans for the rest of the session, and act if something needs doing. If nothing does, reply with exactly NOTHING_TO_DO and nothing else.'
NOTHING_TO_DO = 'NOTHING_TO_DO'


class BuiltInJobs:
    """Makes a desk's built-in jobs."""

    def jobs(
        self,
        heartbeat_minutes: int | None,
        rollover_time: str,
    ) -> list[cron_job_module.CronJob]:
        """The built-in jobs for a desk's settings.

        Args:
            heartbeat_minutes (int | None): Minutes between heartbeats during market hours, or None for no heartbeat.
            rollover_time (str): "HH:MM" India time on trading days when the session rolls over.

        Returns:
            list[cron_job_module.CronJob]: The rollover job, and the heartbeat when it is on.
        """
        hour, minute = rollover_time.split(':')
        jobs = [
            cron_job_module.CronJob(
                job_id='rollover',
                name='After-close rollover',
                kind=cron_job_module.AGENT,
                schedule=f'{int(minute)} {int(hour)} * * *',
                run_at=None,
                text='/rollover',
                trading_days_only=True,
                created_by='built-in',
                catch_up=True,
            ),
        ]
        if heartbeat_minutes is not None:
            jobs.append(
                cron_job_module.CronJob(
                    job_id='heartbeat',
                    name='Heartbeat',
                    kind=cron_job_module.AGENT,
                    schedule=f'*/{heartbeat_minutes} * * * *',
                    run_at=None,
                    text=HEARTBEAT_TEXT,
                    trading_days_only=True,
                    market_hours_only=True,
                    created_by='built-in',
                    catch_up=False,
                )
            )
        return jobs
