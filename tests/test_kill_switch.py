"""Tests for the kill switch, with a fake UBI client in place of the real one."""

import asyncio
import datetime
import zoneinfo
from pathlib import Path

from tradingmachine.unified_broker_interface import exceptions as ubi_exceptions

from trading_agent.risk import kill_switch
from trading_agent.risk import risk_ledger
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module

_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')
_NOW = datetime.datetime(2026, 10, 19, 11, 0, tzinfo=_INDIA)


class _FakeClient:
    """Stands in for UnifiedBrokerInterface, recording the flatten requests.

    Attributes:
        requests: The (path, body) of each POST.
        halt_seen_before_call: Whether the halt was already in the ledger when UBI was called.
    """

    def __init__(
        self, ledger: risk_ledger.RiskLedger, failure: Exception | None = None
    ):
        """Creates the client.

        Args:
            ledger (risk_ledger.RiskLedger): The ledger, checked at the moment of the call.
            failure (Exception | None): An exception to raise, or None to answer normally.
        """
        self._ledger = ledger
        self._failure = failure
        self.requests = []
        self.halt_seen_before_call = None

    def post(self, path: str, body: dict, timeout_seconds: float) -> dict:
        """Records the request.

        Args:
            path (str): The route.
            body (dict): The request body.
            timeout_seconds (float): The timeout, unused.

        Returns:
            dict: A dry-run style answer.

        Raises:
            Exception: The configured failure.
        """
        del timeout_seconds
        self.halt_seen_before_call = (
            self._ledger.active_halt(risk_ledger.ACCOUNT_SCOPE, _NOW.date())
            is not None
        )
        self.requests.append((path, body))
        if self._failure is not None:
            raise self._failure
        return {
            'dry_run': body['dry_run'],
            'would_cancel': [],
            'would_close': [],
        }


class _FakeReader:
    """Stands in for BrokerReader, handing out the fake client."""

    def __init__(self, fake_client: _FakeClient):
        """Creates the reader.

        Args:
            fake_client (_FakeClient): The client to hand out.
        """
        self._client = fake_client

    async def call(self, work):
        """Runs the work at once.

        Args:
            work (Callable): The work.

        Returns:
            object: What the work returned.
        """
        return work()

    def client(self) -> _FakeClient:
        """The fake client.

        Returns:
            _FakeClient: The client.
        """
        return self._client


class _Setup:
    """A kill switch with its fake UBI client, ledger and event subscription.

    Attributes:
        ledger: The real ledger.
        client: The fake UBI client.
        subscription: A subscription to the switch's events.
        switch: The kill switch.
    """

    def __init__(
        self, tmp_path: Path, mode: str, failure: Exception | None = None
    ):
        """Builds the switch.

        Args:
            tmp_path (Path): A temporary folder from pytest.
            mode (str): "dry_run" or "live".
            failure (Exception | None): An exception the fake UBI raises, or None.
        """
        self.ledger = risk_ledger.RiskLedger(tmp_path / 'risk_ledger.db')
        self.client = _FakeClient(self.ledger, failure)
        event_bus = event_bus_module.EventBus()
        self.subscription = event_bus.subscribe()
        self.switch = kill_switch.KillSwitch(
            _FakeReader(self.client), self.ledger, event_bus, mode
        )


class TestKillSwitch:
    """Tests for firing the kill switch."""

    def test_dry_run_mode_sends_a_dry_run_flatten(self, tmp_path: Path) -> None:
        """In dry_run mode UBI is asked only to report what it would do.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path, 'dry_run')

        outcome = asyncio.run(
            setup.switch.trigger('test', datetime.date(2026, 10, 20), _NOW)
        )

        assert setup.client.requests[0][1] == {
            'confirm': 'FLATTEN',
            'dry_run': True,
        }
        assert outcome['dry_run'] is True

    def test_halt_is_recorded_before_ubi_is_called(
        self, tmp_path: Path
    ) -> None:
        """The halt is already in the ledger when the flatten request goes out.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path, 'live')

        asyncio.run(
            setup.switch.trigger('test', datetime.date(2026, 10, 20), _NOW)
        )

        assert setup.client.halt_seen_before_call is True
        assert setup.client.requests[0][1]['dry_run'] is False

    def test_it_fires_only_once_while_halted(self, tmp_path: Path) -> None:
        """A second trigger on the same day does not call UBI again.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path, 'dry_run')

        asyncio.run(
            setup.switch.trigger('first', datetime.date(2026, 10, 20), _NOW)
        )
        second = asyncio.run(
            setup.switch.trigger('second', datetime.date(2026, 10, 20), _NOW)
        )

        assert len(setup.client.requests) == 1
        assert second == {
            'already_halted': 'first',
        }

    def test_ubi_failure_is_reported_and_the_halt_stays(
        self, tmp_path: Path
    ) -> None:
        """If the flatten fails, the outcome says so, and the account stays halted.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(
            tmp_path,
            'live',
            ubi_exceptions.UnreachableError('timed out', None, None),
        )

        outcome = asyncio.run(
            setup.switch.trigger('test', datetime.date(2026, 10, 20), _NOW)
        )

        assert 'UnreachableError' in outcome['error']
        assert (
            setup.ledger.active_halt(risk_ledger.ACCOUNT_SCOPE, _NOW.date())
            == 'test'
        )

    def test_firing_and_outcome_are_published(self, tmp_path: Path) -> None:
        """Two kill_switch events are published: fired, then flatten_finished.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path, 'dry_run')

        asyncio.run(
            setup.switch.trigger('test', datetime.date(2026, 10, 20), _NOW)
        )

        stages = []
        while not setup.subscription._queue.empty():
            published = setup.subscription._queue.get_nowait()
            assert published.kind == event_module.EventKind.KILL_SWITCH
            stages.append(published.payload['stage'])
        assert stages == [
            'fired',
            'flatten_finished',
        ]
