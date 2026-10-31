"""Keeps one trader's scheduled jobs and the record of their runs.

  traders/<trader>/cron/
    jobs.json     the jobs the user or the trader created
    state.json    when each job, built-in ones included, last ran
    runs.jsonl    one line per run: when, which job, and how it went

jobs.json is JSON rather than the plan's TOML, because the trader's tools write it and Python's standard library reads TOML but cannot write it. The user can still edit it by hand.

Typical usage example:

  store = CronJobStore(Path('workspace/traders/main/cron'))
  store.add(job)
  store.record_run(job, moment, 'started', '')
"""

import datetime
import json
import logging
import os
from pathlib import Path
from typing import Any

from trading_agent.scheduling import cron_job as cron_job_module

_LOGGER = logging.getLogger(__name__)


class CronJobStore:
    """One trader's cron folder."""

    def __init__(self, directory: Path):
        """Describes the folder without touching the disk.

        Args:
            directory (Path): The trader's cron folder.
        """
        self.directory = directory
        self._jobs_file = directory / 'jobs.json'
        self._state_file = directory / 'state.json'
        self._runs_file = directory / 'runs.jsonl'

    def jobs(self) -> list[cron_job_module.CronJob]:
        """Reads the jobs; a job that is not valid is logged and left out.

        Returns:
            list[cron_job_module.CronJob]: The jobs, in file order.
        """
        jobs = []
        for data in self._read_json(self._jobs_file, []):
            try:
                jobs.append(cron_job_module.CronJob.from_json_dictionary(data))
            except (cron_job_module.CronJobError, TypeError) as error:
                _LOGGER.warning(
                    'Skipped a cron job in %s: %s', self._jobs_file, error
                )
        return jobs

    def add(self, job: cron_job_module.CronJob) -> None:
        """Adds a job.

        Args:
            job (cron_job_module.CronJob): The job.
        """
        jobs = self.jobs()
        jobs.append(job)
        self._write_jobs(jobs)

    def delete(self, job_id: str) -> cron_job_module.CronJob | None:
        """Removes a job.

        Args:
            job_id (str): The job's identifier.

        Returns:
            cron_job_module.CronJob | None: The removed job, or None when there was none with that id.
        """
        kept = []
        removed = None
        for job in self.jobs():
            if job.job_id == job_id:
                removed = job
            else:
                kept.append(job)
        if removed is not None:
            self._write_jobs(kept)
        return removed

    def last_run(self, job_id: str) -> datetime.datetime | None:
        """When a job last ran.

        Args:
            job_id (str): The job's identifier.

        Returns:
            datetime.datetime | None: The moment, or None when it never ran.
        """
        text = self._read_json(self._state_file, {}).get(job_id)
        if not text:
            return None
        try:
            return datetime.datetime.fromisoformat(text)
        except ValueError:
            return None

    def record_run(
        self,
        job: cron_job_module.CronJob,
        moment: datetime.datetime,
        outcome: str,
        detail: str,
    ) -> None:
        """Records that a job ran, or was skipped, at a moment.

        Args:
            job (cron_job_module.CronJob): The job.
            moment (datetime.datetime): The scheduled moment it ran for.
            outcome (str): Such as "started", "skipped" or "failed".
            detail (str): More about it, or an empty string.
        """
        self.directory.mkdir(parents=True, exist_ok=True)
        state = self._read_json(self._state_file, {})
        state[job.job_id] = moment.isoformat()
        self._write_json(self._state_file, state)
        line = json.dumps(
            {
                'at': moment.isoformat(),
                'job_id': job.job_id,
                'name': job.name,
                'outcome': outcome,
                'detail': detail,
            },
            ensure_ascii=False,
        )
        with self._runs_file.open('a', encoding='utf-8') as runs:
            runs.write(line + '\n')

    def recent_runs(self, limit: int) -> list[dict[str, Any]]:
        """The latest runs and skips, newest first.

        Args:
            limit (int): The most runs.

        Returns:
            list[dict[str, Any]]: Each run's time, job id, name, outcome and detail.
        """
        if not self._runs_file.is_file():
            return []
        runs = []
        for line in self._runs_file.read_text(encoding='utf-8').splitlines()[
            -limit:
        ]:
            try:
                runs.append(json.loads(line))
            except ValueError:
                continue
        runs.reverse()
        return runs

    def forget_run(self, job_id: str) -> None:
        """Drops a job's last-run time, after the job is deleted.

        Args:
            job_id (str): The job's identifier.
        """
        state = self._read_json(self._state_file, {})
        if state.pop(job_id, None) is not None:
            self._write_json(self._state_file, state)

    def _write_jobs(self, jobs: list[cron_job_module.CronJob]) -> None:
        """Writes the jobs file.

        Args:
            jobs (list[cron_job_module.CronJob]): The jobs.
        """
        data = []
        for job in jobs:
            data.append(job.to_json_dictionary())
        self._write_json(self._jobs_file, data)

    def _read_json(self, path: Path, default: Any) -> Any:
        """Reads a JSON file, or returns a default when it is missing or damaged.

        Args:
            path (Path): The file.
            default (Any): What to return instead.

        Returns:
            Any: The parsed content, or the default.
        """
        if not path.is_file():
            return default
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except OSError, ValueError:
            _LOGGER.exception('Could not read %s', path)
            return default

    def _write_json(self, path: Path, data: Any) -> None:
        """Writes a JSON file through a temporary file, so a crash cannot leave half of it.

        Args:
            path (Path): The file.
            data (Any): The content.
        """
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + '.tmp')
        temporary.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8'
        )
        os.replace(temporary, path)
