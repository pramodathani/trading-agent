"""Tests for the gateway API's route groups, each mounted alone on a small FastAPI application."""

import datetime
import zoneinfo
from pathlib import Path
from typing import Any

import fastapi
import fastapi.testclient

from trading_agent.configuration import agent_configuration
from trading_agent.gateway import access_guard
from trading_agent.gateway import gateway_application
from trading_agent.gateway import gateway_parts
from trading_agent.gateway.routes import account_routes
from trading_agent.gateway.routes import extension_routes
from trading_agent.gateway.routes import file_routes
from trading_agent.gateway.routes import memory_routes
from trading_agent.gateway.routes import route_group
from trading_agent.gateway.routes import schedule_routes
from trading_agent.gateway.routes import system_routes
from trading_agent.journal import secret_redactor
from trading_agent.journal import usage_tracker
from trading_agent.memory import checkpoints as checkpoints_module
from trading_agent.memory import session_store
from trading_agent.runtime import desk_runtime
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import no_model_turn_runner
from trading_agent.scheduling import cron_job
from trading_agent.scheduling import cron_job_store
from trading_agent.scheduling import price_alert_store
from trading_agent.workspace import proposal_store
from trading_agent.workspace import workspace_layout

_TOKEN = 'test-token-that-is-long-enough-1234567890'
_HEADERS = {
    'Authorization': f'Bearer {_TOKEN}',
}
_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')
_NEXT_RUN = datetime.datetime(2026, 10, 19, 9, 5, tzinfo=_INDIA)


class _StandInScheduler:
    """A cron scheduler that gives a fixed next run and records jobs started now."""

    def __init__(self):
        """Creates the stand-in with nothing started."""
        self.started: list[tuple[str, str]] = []

    def upcoming(
        self, job: cron_job.CronJob, count: int
    ) -> list[datetime.datetime]:
        """Gives one fixed next run.

        Args:
            job (cron_job.CronJob): The job.
            count (int): How many runs were asked for.

        Returns:
            list[datetime.datetime]: The fixed run.
        """
        del job, count
        return [
            _NEXT_RUN,
        ]

    async def run_now(self, desk_name: str, job_id: str) -> bool:
        """Records a job started now, when it is the known one.

        Args:
            desk_name (str): The desk.
            job_id (str): The job.

        Returns:
            bool: True for the job "heartbeat", False for any other.
        """
        if job_id != 'heartbeat':
            return False
        self.started.append((desk_name, job_id))
        return True


class _StandInKillSwitch:
    """A kill switch that records each time it fires."""

    def __init__(self):
        """Creates the stand-in, not yet fired."""
        self.reasons: list[str] = []

    async def trigger(
        self,
        reason: str,
        until_date: datetime.date,
        now: datetime.datetime,
    ) -> dict[str, Any]:
        """Records the reason.

        Args:
            reason (str): Why.
            until_date (datetime.date): The first day trading is allowed again.
            now (datetime.datetime): The current time.

        Returns:
            dict[str, Any]: A made-up flatten answer.
        """
        del until_date, now
        self.reasons.append(reason)
        return {
            'flattened': True,
        }


class _StandInUsage:
    """A usage tracker with one backend's usage for every desk."""

    def today(self, desk_name: str) -> dict[str, usage_tracker.BackendUsage]:
        """Gives the same usage for every desk.

        Args:
            desk_name (str): The desk.

        Returns:
            dict[str, usage_tracker.BackendUsage]: Two calls to qwen.
        """
        del desk_name
        return {
            'qwen': usage_tracker.BackendUsage(calls=2, prompt_tokens=300),
        }

    def rate_limits(self) -> dict[str, dict[str, Any]]:
        """Gives no rate-limit reports.

        Returns:
            dict[str, dict[str, Any]]: An empty dictionary.
        """
        return {}


class _Workspace:
    """A real workspace with one desk, and that desk's real stores."""

    def __init__(self, directory: Path):
        """Creates the workspace files and stores.

        Args:
            directory (Path): An empty folder.
        """
        self.layout = workspace_layout.WorkspaceLayout(directory)
        self.layout.create_missing(
            [
                'main',
            ]
        )
        self.scheduler = _StandInScheduler()
        self.kill_switch = _StandInKillSwitch()
        self.checkpoints = checkpoints_module.Checkpoints(
            directory / '.checkpoints' / 'main.git',
            self.layout.desk_directory('main'),
        )
        self.parts = {
            'main': gateway_parts.DeskParts(
                sessions=session_store.SessionStore(directory / 'sessions'),
                jobs=cron_job_store.CronJobStore(directory / 'cron'),
                built_in_jobs=[
                    cron_job.CronJob(
                        job_id='heartbeat',
                        name='heartbeat',
                        kind=cron_job.AGENT,
                        schedule='*/10 9-15 * * 1-5',
                        run_at=None,
                        text='Heartbeat.',
                        created_by='built-in',
                    ),
                ],
                alerts=price_alert_store.PriceAlertStore(
                    directory / 'alerts.json'
                ),
                skills=None,
                checkpoints=self.checkpoints,
                tools=None,
            ),
        }
        self.shared = gateway_parts.SharedParts(
            layout=self.layout,
            reader=None,
            snapshot_reader=None,
            risk_engine=None,
            ledger=None,
            kill_switch=self.kill_switch,
            order_book=None,
            proposals=proposal_store.ProposalStore(self.layout),
            subagents=None,
            packages=None,
            calendar=None,
        )

    def client(
        self, group: route_group.RouteGroup
    ) -> fastapi.testclient.TestClient:
        """Mounts one route group on its own application.

        Args:
            group (route_group.RouteGroup): The routes.

        Returns:
            fastapi.testclient.TestClient: A client for them.
        """
        application = fastapi.FastAPI()
        application.include_router(group.router())
        return fastapi.testclient.TestClient(application)


def _guard() -> access_guard.AccessGuard:
    """Builds the guard every test uses.

    Returns:
        access_guard.AccessGuard: A guard for the test token.
    """
    return access_guard.AccessGuard(_TOKEN)


class TestFileRoutes:
    """Tests for the file and proposal routes."""

    def _client(self, workspace: _Workspace) -> fastapi.testclient.TestClient:
        """Builds a client for the file routes.

        Args:
            workspace (_Workspace): The workspace.

        Returns:
            fastapi.testclient.TestClient: The client.
        """
        return workspace.client(
            file_routes.FileRoutes(
                _guard(),
                workspace.layout,
                workspace.parts,
                workspace.shared.proposals,
            )
        )

    def test_files_need_the_token(self, tmp_path: Path) -> None:
        """Listing the files without the token gets HTTP 401."""
        client = self._client(_Workspace(tmp_path))

        assert client.get('/api/files').status_code == 401

    def test_unreadable_trading_rules_are_not_saved(
        self, tmp_path: Path
    ) -> None:
        """A TradingRules.md whose limits the risk engine cannot read is refused and the old file is kept."""
        workspace = _Workspace(tmp_path)
        rules_file = workspace.layout.user_owned_file('', 'TradingRules.md')
        before = rules_file.read_text(encoding='utf-8')
        client = self._client(workspace)

        response = client.put(
            '/api/files/content',
            headers=_HEADERS,
            json={
                'name': 'TradingRules.md',
                'desk': None,
                'text': 'Trade carefully.',
            },
        )

        assert response.status_code == 400
        assert 'Not saved' in response.json()['detail']
        assert rules_file.read_text(encoding='utf-8') == before

    def test_readable_trading_rules_are_saved(self, tmp_path: Path) -> None:
        """A TradingRules.md with valid limits is saved."""
        workspace = _Workspace(tmp_path)
        rules_file = workspace.layout.user_owned_file('', 'TradingRules.md')
        new_text = rules_file.read_text(encoding='utf-8') + '\nOne more rule.\n'
        client = self._client(workspace)

        response = client.put(
            '/api/files/content',
            headers=_HEADERS,
            json={
                'name': 'TradingRules.md',
                'desk': None,
                'text': new_text,
            },
        )

        assert response.status_code == 200
        assert rules_file.read_text(encoding='utf-8') == new_text

    def test_memory_edit_is_checkpointed_first(self, tmp_path: Path) -> None:
        """Editing a desk's Memory.md takes a snapshot first, so the edit can be undone."""
        workspace = _Workspace(tmp_path)
        client = self._client(workspace)

        response = client.put(
            '/api/files/content',
            headers=_HEADERS,
            json={
                'name': 'Memory.md',
                'desk': 'main',
                'text': 'Remember the gap rule.',
            },
        )
        read_back = client.get(
            '/api/files/content',
            headers=_HEADERS,
            params={
                'name': 'Memory.md',
                'desk': 'main',
            },
        )

        assert response.status_code == 200
        assert read_back.json()['text'] == 'Remember the gap rule.'
        reasons = [
            checkpoint.reason for checkpoint in workspace.checkpoints.list()
        ]
        assert 'before the user edited Memory.md' in reasons

    def test_other_files_cannot_be_written(self, tmp_path: Path) -> None:
        """A name that is not one of the user's files is refused."""
        client = self._client(_Workspace(tmp_path))

        response = client.put(
            '/api/files/content',
            headers=_HEADERS,
            json={
                'name': '../../.env',
                'desk': None,
                'text': 'stolen',
            },
        )

        assert response.status_code == 400


class TestScheduleRoutes:
    """Tests for the job and alert routes."""

    def _client(self, workspace: _Workspace) -> fastapi.testclient.TestClient:
        """Builds a client for the schedule routes.

        Args:
            workspace (_Workspace): The workspace.

        Returns:
            fastapi.testclient.TestClient: The client.
        """
        return workspace.client(
            schedule_routes.ScheduleRoutes(
                _guard(),
                workspace.parts,
                workspace.scheduler,
            )
        )

    def test_created_job_is_listed_with_its_next_run(
        self, tmp_path: Path
    ) -> None:
        """A job created through the API is listed after the built-in heartbeat, with its next run."""
        client = self._client(_Workspace(tmp_path))

        created = client.post(
            '/api/desks/main/jobs',
            headers=_HEADERS,
            json={
                'name': 'morning scan',
                'schedule': '50 8 * * 1-5',
                'instructions': 'Scan the gap-ups.',
            },
        )
        listing = client.get('/api/desks/main/jobs', headers=_HEADERS)

        assert created.status_code == 201
        assert created.json()['created_by'] == 'user'
        names = [job['name'] for job in listing.json()['jobs']]
        assert names == [
            'heartbeat',
            'morning scan',
        ]
        assert listing.json()['jobs'][1]['next_runs'] == [
            _NEXT_RUN.isoformat(),
        ]

    def test_job_needs_instructions_or_command_not_both(
        self, tmp_path: Path
    ) -> None:
        """A job with both instructions and a command is refused."""
        client = self._client(_Workspace(tmp_path))

        response = client.post(
            '/api/desks/main/jobs',
            headers=_HEADERS,
            json={
                'name': 'confused',
                'schedule': '0 9 * * 1-5',
                'instructions': 'Do it.',
                'command': 'echo it',
            },
        )

        assert response.status_code == 400

    def test_bad_cron_expression_is_refused(self, tmp_path: Path) -> None:
        """A schedule that is not a cron expression is refused with the reason."""
        client = self._client(_Workspace(tmp_path))

        response = client.post(
            '/api/desks/main/jobs',
            headers=_HEADERS,
            json={
                'name': 'broken',
                'schedule': 'every morning',
                'instructions': 'Do it.',
            },
        )

        assert response.status_code == 400

    def test_built_in_job_cannot_be_deleted(self, tmp_path: Path) -> None:
        """Deleting the heartbeat is refused, because it is set in trading_agent.toml."""
        client = self._client(_Workspace(tmp_path))

        response = client.delete(
            '/api/desks/main/jobs/heartbeat', headers=_HEADERS
        )

        assert response.status_code == 400

    def test_user_job_can_be_deleted(self, tmp_path: Path) -> None:
        """A job created through the API can be deleted, and is then gone."""
        client = self._client(_Workspace(tmp_path))
        created = client.post(
            '/api/desks/main/jobs',
            headers=_HEADERS,
            json={
                'name': 'one-off',
                'schedule': '0 12 * * 1-5',
                'command': 'date',
            },
        )
        job_id = created.json()['job_id']

        deleted = client.delete(
            f'/api/desks/main/jobs/{job_id}', headers=_HEADERS
        )
        again = client.delete(
            f'/api/desks/main/jobs/{job_id}', headers=_HEADERS
        )

        assert deleted.status_code == 200
        assert again.status_code == 404

    def test_run_now_starts_a_known_job(self, tmp_path: Path) -> None:
        """Run now starts a known job and answers 404 for an unknown one."""
        workspace = _Workspace(tmp_path)
        client = self._client(workspace)

        started = client.post(
            '/api/desks/main/jobs/heartbeat/run', headers=_HEADERS
        )
        unknown = client.post(
            '/api/desks/main/jobs/nothing/run', headers=_HEADERS
        )

        assert started.status_code == 200
        assert unknown.status_code == 404
        assert workspace.scheduler.started == [
            (
                'main',
                'heartbeat',
            ),
        ]

    def test_alert_can_be_listed_and_removed(self, tmp_path: Path) -> None:
        """A price alert is listed and can be removed once."""
        workspace = _Workspace(tmp_path)
        alert = price_alert_store.PriceAlert.new(
            instrument_id='NSE:EQ:IDEA',
            exchange='NSE',
            segment='EQ',
            symbol='IDEA',
            condition=price_alert_store.ABOVE,
            price=13.0,
            note='breakout',
        )
        workspace.parts['main'].alerts.add(alert)
        client = self._client(workspace)

        listing = client.get('/api/desks/main/alerts', headers=_HEADERS)
        removed = client.delete(
            f'/api/desks/main/alerts/{alert.alert_id}', headers=_HEADERS
        )
        again = client.delete(
            f'/api/desks/main/alerts/{alert.alert_id}', headers=_HEADERS
        )

        assert listing.json()['alerts'][0]['alert_id'] == alert.alert_id
        assert removed.status_code == 200
        assert again.status_code == 404


class TestExtensionRoutes:
    """Tests for the checkpoint routes."""

    def test_checkpoint_can_be_restored(self, tmp_path: Path) -> None:
        """Restoring a snapshot puts Memory.md back and reports the snapshot that undoes it."""
        workspace = _Workspace(tmp_path)
        memory_file = workspace.layout.memory_file('main')
        memory_file.write_text('First version.', encoding='utf-8')
        first = workspace.checkpoints.snapshot('first')
        memory_file.write_text('Second version.', encoding='utf-8')
        client = workspace.client(
            extension_routes.ExtensionRoutes(
                _guard(),
                workspace.parts,
                workspace.shared,
                None,
            )
        )

        listing = client.get('/api/desks/main/checkpoints', headers=_HEADERS)
        restored = client.post(
            f'/api/desks/main/checkpoints/{first}/restore', headers=_HEADERS
        )

        assert listing.json()['checkpoints'][0]['reason'] == 'first'
        assert restored.status_code == 200
        assert restored.json()['undo_checkpoint_id']
        assert memory_file.read_text(encoding='utf-8') == 'First version.'

    def test_checkpoint_id_must_look_like_one(self, tmp_path: Path) -> None:
        """A checkpoint id that is not a git hash is refused before git is run."""
        workspace = _Workspace(tmp_path)
        client = workspace.client(
            extension_routes.ExtensionRoutes(
                _guard(),
                workspace.parts,
                workspace.shared,
                None,
            )
        )

        response = client.post(
            '/api/desks/main/checkpoints/--help/restore', headers=_HEADERS
        )

        assert response.status_code == 422


class TestAccountRoutes:
    """Tests for the kill switch route."""

    def _client(self, workspace: _Workspace) -> fastapi.testclient.TestClient:
        """Builds a client for the account routes.

        Args:
            workspace (_Workspace): The workspace.

        Returns:
            fastapi.testclient.TestClient: The client.
        """
        return workspace.client(
            account_routes.AccountRoutes(
                _guard(),
                workspace.shared,
                [
                    'main',
                ],
            )
        )

    def test_kill_needs_the_confirmation_word(self, tmp_path: Path) -> None:
        """The kill switch does not fire without the word FLATTEN."""
        workspace = _Workspace(tmp_path)
        client = self._client(workspace)

        response = client.post(
            '/api/account/kill',
            headers=_HEADERS,
            json={
                'confirm': 'yes',
                'reason': 'testing',
            },
        )

        assert response.status_code == 400
        assert workspace.kill_switch.reasons == []

    def test_kill_fires_with_the_confirmation_word(
        self, tmp_path: Path
    ) -> None:
        """With FLATTEN, the kill switch fires with the user's reason."""
        workspace = _Workspace(tmp_path)
        client = self._client(workspace)

        response = client.post(
            '/api/account/kill',
            headers=_HEADERS,
            json={
                'confirm': 'FLATTEN',
                'reason': 'market crash',
            },
        )

        assert response.status_code == 200
        assert workspace.kill_switch.reasons == [
            'The user fired the kill switch: market crash',
        ]


class TestMemoryRoutes:
    """Tests for the session routes."""

    def test_session_id_must_look_like_one(self, tmp_path: Path) -> None:
        """A session id that could reach outside the sessions folder is refused."""
        workspace = _Workspace(tmp_path)
        client = workspace.client(
            memory_routes.MemoryRoutes(
                _guard(),
                workspace.parts,
                workspace.layout,
            )
        )

        response = client.get(
            '/api/desks/main/sessions/..%2F..%2Fsecrets', headers=_HEADERS
        )

        assert response.status_code in (
            400,
            404,
        )

    def test_unknown_desk_is_404(self, tmp_path: Path) -> None:
        """Asking for the sessions of a desk that does not exist gets HTTP 404."""
        workspace = _Workspace(tmp_path)
        client = workspace.client(
            memory_routes.MemoryRoutes(
                _guard(),
                workspace.parts,
                workspace.layout,
            )
        )

        response = client.get('/api/desks/nowhere/sessions', headers=_HEADERS)

        assert response.status_code == 404


class TestSystemRoutes:
    """Tests for the usage and configuration routes."""

    def _client(self, tmp_path: Path) -> fastapi.testclient.TestClient:
        """Builds a client for the system routes, with a secret in the configuration.

        Args:
            tmp_path (Path): A scratch folder.

        Returns:
            fastapi.testclient.TestClient: The client.
        """
        configuration = agent_configuration.AgentConfiguration(
            tradingmachine_environment_file=tmp_path / 'tm.env',
            desks=[
                agent_configuration.DeskConfiguration(name='main'),
            ],
            backends={
                'remote': agent_configuration.BackendConfiguration(
                    kind='openai_compatible',
                    base_url='https://user:hunter2-secret-value@example.com/v1',
                    model='some-model',
                    context_window=8000,
                ),
            },
        )
        group = system_routes.SystemRoutes(
            _guard(),
            configuration,
            _StandInUsage(),
            secret_redactor.SecretRedactor(
                [
                    'hunter2-secret-value',
                ]
            ),
            [
                'main',
            ],
        )
        application = fastapi.FastAPI()
        application.include_router(group.router())
        return fastapi.testclient.TestClient(application)

    def test_configuration_masks_secrets(self, tmp_path: Path) -> None:
        """A secret inside the configuration is masked."""
        client = self._client(tmp_path)

        response = client.get('/api/configuration', headers=_HEADERS)

        assert response.status_code == 200
        assert 'hunter2-secret-value' not in response.text
        assert response.json()['backends']['remote']['model'] == 'some-model'

    def test_usage_is_given_per_desk_and_backend(self, tmp_path: Path) -> None:
        """Usage is reported for each desk, by backend."""
        client = self._client(tmp_path)

        response = client.get('/api/usage', headers=_HEADERS)

        assert response.json()['desks']['main']['qwen']['calls'] == 2


class TestEventFilter:
    """Tests for the desk filter on the event stream."""

    def test_desk_filter_sends_only_that_desks_events(self) -> None:
        """With ?desk=main, the other desk's events are not sent."""
        event_bus = event_bus_module.EventBus()
        desks = {}
        for name in ('main', 'other'):
            desks[name] = desk_runtime.DeskRuntime(
                agent_configuration.DeskConfiguration(name=name),
                event_bus,
                no_model_turn_runner.NoModelTurnRunner(),
            )
        gateway = gateway_application.GatewayApplication(
            event_bus, desks, _guard()
        )
        address = f'/ws/events?token={_TOKEN}&desk=main'
        with (
            fastapi.testclient.TestClient(gateway.build()) as client,
            client.websocket_connect(address) as websocket,
        ):
            client.post(
                '/api/desks/other/messages',
                headers=_HEADERS,
                json={
                    'text': 'for other',
                },
            )
            client.post(
                '/api/desks/main/messages',
                headers=_HEADERS,
                json={
                    'text': 'for main',
                },
            )
            received = []
            while not received or received[-1]['kind'] != 'turn_finished':
                received.append(websocket.receive_json())

        desks_seen = {event['desk'] for event in received}
        assert desks_seen == {
            'main',
        }
