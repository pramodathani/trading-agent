"""The two jobs every desk gets from trading_agent.toml rather than from its jobs file.

- The heartbeat wakes the desk every few minutes while NSE equities trade, to look at its positions, orders and plans. It is off unless the desk's heartbeat_minutes is set, because every heartbeat is a model turn. A heartbeat the desk answers with NOTHING_TO_DO produces no message.
- The rollover runs /rollover after the close on trading days, 15:45 by default, so the day's summary and the skill review happen right after the market shuts instead of with the next morning's first message.
- Each scheduled check wakes the desk at a set time on trading days, such as 09:05, to follow its Persona.md's routine for that time; the desk may answer NOTHING_TO_DO.

Typical usage example:

  jobs = BuiltInJobs().jobs(heartbeat_minutes=15, rollover_time='15:45')
"""

from trading_agent.scheduling import cron_job as cron_job_module

HEARTBEAT_TEXT = '[Heartbeat] Look at your open positions, orders, price alerts and plans for the rest of the session, and act if something needs doing. If nothing does, reply with exactly NOTHING_TO_DO and nothing else.'
NOTHING_TO_DO = 'NOTHING_TO_DO'
CHECK_TEXT = '[Scheduled check at {time}] Do what your Persona.md says for this time of day. If nothing needs doing, reply with exactly NOTHING_TO_DO and nothing else.'


class BuiltInJobs:
    """Makes a desk's built-in jobs."""

    def jobs(
        self,
        heartbeat_minutes: int | None,
        rollover_time: str,
        scheduled_checks: list[str] | None = None,
    ) -> list[cron_job_module.CronJob]:
        """The built-in jobs for a desk's settings.

        Args:
            heartbeat_minutes (int | None): Minutes between heartbeats during market hours, or None for no heartbeat.
            rollover_time (str): "HH:MM" India time on trading days when the session rolls over.
            scheduled_checks (list[str] | None): "HH:MM" India times on trading days for the desk's routine checks.

        Returns:
            list[cron_job_module.CronJob]: The rollover job, each scheduled check, and the heartbeat when it is on.
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
        for check_time in scheduled_checks or []:
            check_hour, check_minute = check_time.split(':')
            jobs.append(
                cron_job_module.CronJob(
                    job_id=f'check-{check_hour}{check_minute}',
                    name=f'Scheduled check at {check_time}',
                    kind=cron_job_module.AGENT,
                    schedule=f'{int(check_minute)} {int(check_hour)} * * *',
                    run_at=None,
                    text=CHECK_TEXT.format(time=check_time),
                    trading_days_only=True,
                    created_by='built-in',
                    catch_up=False,
                )
            )
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
