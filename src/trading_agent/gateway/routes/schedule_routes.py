"""Routes for each trader's scheduled jobs and price alerts.

  GET    /api/traders/{trader}/jobs              the jobs, built-in ones included, with their next runs, and the recent runs
  POST   /api/traders/{trader}/jobs              create a job, as cron_create does
  DELETE /api/traders/{trader}/jobs/{job_id}     delete a job; the built-in ones cannot be deleted here
  POST   /api/traders/{trader}/jobs/{job_id}/run start a job now
  GET    /api/traders/{trader}/alerts            the trader's price alerts
  DELETE /api/traders/{trader}/alerts/{alert_id} remove an alert

Typical usage example:

  application.include_router(ScheduleRoutes(guard, parts, scheduler).router())
"""

import dataclasses
from collections.abc import Mapping
from typing import Any

import fastapi
import pydantic

from trading_agent.gateway import access_guard
from trading_agent.gateway import gateway_parts
from trading_agent.gateway.routes import route_group
from trading_agent.scheduling import cron_job
from trading_agent.scheduling import cron_scheduler as cron_scheduler_module

_RECENT_RUNS = 50


class JobRequest(pydantic.BaseModel):
    """The body of a new job.

    Attributes:
        name: A short name.
        schedule: Five cron fields in India time, or None for a one-off job.
        run_at: The ISO 8601 time of a one-off job, or None.
        instructions: For an agent job, the message or the subagent's task.
        command: For a command job instead, the shell command.
        target: "trader" or "subagent:<name>".
        trading_days_only: Whether to skip weekends and exchange holidays.
        market_hours_only: Whether to run only while NSE equities trade.
        deliver_url: An address to POST the result to, or None.
    """

    name: str = pydantic.Field(min_length=1, max_length=80)
    schedule: str | None = None
    run_at: str | None = None
    instructions: str | None = None
    command: str | None = None
    target: str = cron_job.TRADER_TARGET
    trading_days_only: bool = True
    market_hours_only: bool = False
    deliver_url: str | None = None


class ScheduleRoutes(route_group.RouteGroup):
    """The job and alert routes."""

    def __init__(
        self,
        guard: access_guard.AccessGuard,
        parts: Mapping[str, gateway_parts.TraderParts],
        scheduler: cron_scheduler_module.CronScheduler,
    ):
        """Creates the routes.

        Args:
            guard (access_guard.AccessGuard): Checks the access token.
            parts (Mapping[str, gateway_parts.TraderParts]): Each trader's stores.
            scheduler (cron_scheduler_module.CronScheduler): Works out next runs and starts jobs now.
        """
        super().__init__(guard)
        self._parts = parts
        self._scheduler = scheduler

    def _add_routes(self, router: fastapi.APIRouter) -> None:
        """Adds the schedule routes.

        Args:
            router (fastapi.APIRouter): The router.
        """
        router.add_api_route(
            '/api/traders/{trader_name}/jobs', self.list_jobs, methods=['GET']
        )
        router.add_api_route(
            '/api/traders/{trader_name}/jobs',
            self.create_job,
            methods=['POST'],
            status_code=201,
        )
        router.add_api_route(
            '/api/traders/{trader_name}/jobs/{job_id}',
            self.delete_job,
            methods=['DELETE'],
        )
        router.add_api_route(
            '/api/traders/{trader_name}/jobs/{job_id}/run',
            self.run_job,
            methods=['POST'],
        )
        router.add_api_route(
            '/api/traders/{trader_name}/alerts',
            self.list_alerts,
            methods=['GET'],
        )
        router.add_api_route(
            '/api/traders/{trader_name}/alerts/{alert_id}',
            self.delete_alert,
            methods=['DELETE'],
        )

    def list_jobs(self, trader_name: str) -> dict[str, Any]:
        """The trader's jobs and recent runs.

        Args:
            trader_name (str): The trader.

        Returns:
            dict[str, Any]: Each job with its description, next three runs and last run, and the latest runs.
        """
        parts = self._find(self._parts, trader_name, 'trader')
        jobs = []
        for job in [*parts.built_in_jobs, *parts.jobs.jobs()]:
            entry = dataclasses.asdict(job)
            entry['description'] = job.describe()
            entry['next_runs'] = [
                moment.isoformat()
                for moment in self._scheduler.upcoming(job, 3)
            ]
            last_run = parts.jobs.last_run(job.job_id)
            entry['last_run'] = last_run.isoformat() if last_run else None
            jobs.append(entry)
        return {
            'jobs': jobs,
            'recent_runs': parts.jobs.recent_runs(_RECENT_RUNS),
        }

    def create_job(
        self, trader_name: str, request: JobRequest
    ) -> dict[str, Any]:
        """Creates a job.

        Args:
            trader_name (str): The trader.
            request (JobRequest): The job.

        Returns:
            dict[str, Any]: The job, with its description and next runs.

        Raises:
            fastapi.HTTPException: The job is not valid (status 400).
        """
        parts = self._find(self._parts, trader_name, 'trader')
        if (request.instructions is None) == (request.command is None):
            raise fastapi.HTTPException(
                status_code=400, detail='Give instructions or command, not both'
            )
        kind = cron_job.AGENT if request.command is None else cron_job.COMMAND
        try:
            job = cron_job.CronJob.new(
                name=request.name,
                kind=kind,
                schedule=request.schedule,
                run_at=request.run_at,
                text=request.instructions or request.command,
                target=request.target,
                trading_days_only=request.trading_days_only,
                market_hours_only=request.market_hours_only,
                deliver_url=request.deliver_url,
                created_by='user',
            )
        except cron_job.CronJobError as error:
            raise fastapi.HTTPException(
                status_code=400, detail=str(error)
            ) from error
        parts.jobs.add(job)
        entry = dataclasses.asdict(job)
        entry['description'] = job.describe()
        entry['next_runs'] = [
            moment.isoformat() for moment in self._scheduler.upcoming(job, 3)
        ]
        return entry

    def delete_job(self, trader_name: str, job_id: str) -> dict[str, Any]:
        """Deletes a job.

        Args:
            trader_name (str): The trader.
            job_id (str): The job.

        Returns:
            dict[str, Any]: The deleted job's description.

        Raises:
            fastapi.HTTPException: The job is built in (status 400) or unknown (status 404).
        """
        parts = self._find(self._parts, trader_name, 'trader')
        for job in parts.built_in_jobs:
            if job.job_id == job_id:
                raise fastapi.HTTPException(
                    status_code=400,
                    detail='Built-in jobs are set in trading_agent.toml',
                )
        removed = parts.jobs.delete(job_id)
        if removed is None:
            raise fastapi.HTTPException(
                status_code=404, detail=f'No job {job_id!r}'
            )
        parts.jobs.forget_run(job_id)
        return {
            'deleted': removed.describe(),
        }

    async def run_job(self, trader_name: str, job_id: str) -> dict[str, Any]:
        """Starts a job now.

        Args:
            trader_name (str): The trader.
            job_id (str): The job.

        Returns:
            dict[str, Any]: A confirmation; results arrive as events.

        Raises:
            fastapi.HTTPException: The trader or job is unknown (status 404).
        """
        self._find(self._parts, trader_name, 'trader')
        if not await self._scheduler.run_now(trader_name, job_id):
            raise fastapi.HTTPException(
                status_code=404, detail=f'No job {job_id!r}'
            )
        return {
            'started': job_id,
        }

    def list_alerts(self, trader_name: str) -> dict[str, Any]:
        """The trader's price alerts.

        Args:
            trader_name (str): The trader.

        Returns:
            dict[str, Any]: The alerts, oldest first.
        """
        parts = self._find(self._parts, trader_name, 'trader')
        alerts = []
        for alert in parts.alerts.alerts():
            entry = dataclasses.asdict(alert)
            entry['description'] = alert.describe()
            alerts.append(entry)
        return {
            'alerts': alerts,
        }

    def delete_alert(self, trader_name: str, alert_id: str) -> dict[str, Any]:
        """Removes a price alert.

        Args:
            trader_name (str): The trader.
            alert_id (str): The alert.

        Returns:
            dict[str, Any]: The removed alert's description.

        Raises:
            fastapi.HTTPException: The alert is unknown (status 404).
        """
        parts = self._find(self._parts, trader_name, 'trader')
        removed = parts.alerts.remove(alert_id)
        if removed is None:
            raise fastapi.HTTPException(
                status_code=404, detail=f'No alert {alert_id!r}'
            )
        return {
            'deleted': removed.describe(),
        }
