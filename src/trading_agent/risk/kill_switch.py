"""The kill switch: stops every trader and closes every position in the account.

It calls tradingmachine's Account.flatten, which halts UBI's order engine, cancels every open order at every broker and closes every position. tradingmachine warns that a flatten that times out may still have happened, and that calling it twice can close positions twice, so the halt is written to the ledger before UBI is called, and the switch never fires again while that halt is in force. In dry_run mode the flatten is a dry run: UBI reports what it would cancel and close, and sends nothing.

Typical usage example:

  kill_switch = KillSwitch(reader, ledger, event_bus, 'dry_run')
  await kill_switch.trigger('Daily loss limit reached', until_date, now)
"""

import datetime
import logging
from typing import Any

from tradingmachine.accounts import account as account_module
from tradingmachine.unified_broker_interface import exceptions as ubi_exceptions

from trading_agent.risk import risk_ledger as risk_ledger_module
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.trading import broker_reader as broker_reader_module

_LOGGER = logging.getLogger(__name__)
_CONFIRMATION = 'FLATTEN'


class KillSwitch:
    """Halts trading and flattens the account."""

    def __init__(
        self,
        reader: broker_reader_module.BrokerReader,
        ledger: risk_ledger_module.RiskLedger,
        event_bus: event_bus_module.EventBus,
        mode: str,
    ):
        """Creates the switch.

        Args:
            reader (broker_reader_module.BrokerReader): The shared reader, whose client the flatten goes through.
            ledger (risk_ledger_module.RiskLedger): Where the halt is recorded.
            event_bus (event_bus_module.EventBus): Where the switch's firing and its outcome are published.
            mode (str): "dry_run" for a flatten that sends nothing, "live" for a real one.
        """
        self._reader = reader
        self._ledger = ledger
        self._event_bus = event_bus
        self._mode = mode

    async def trigger(
        self,
        reason: str,
        until_date: datetime.date,
        now: datetime.datetime,
    ) -> dict[str, Any]:
        """Halts the account and flattens it, unless a halt is already in force.

        Args:
            reason (str): Why, for the ledger, the journal and the traders.
            until_date (datetime.date): The first day trading is allowed again.
            now (datetime.datetime): The current time.

        Returns:
            dict[str, Any]: UBI's answer to the flatten, an error description, or a note that the switch had already fired.
        """
        today = now.date()
        existing = self._ledger.active_halt(
            risk_ledger_module.ACCOUNT_SCOPE, today
        )
        if existing is not None:
            return {
                'already_halted': existing,
            }
        self._ledger.halt(
            risk_ledger_module.ACCOUNT_SCOPE, reason, until_date, now
        )
        self._publish(
            event_module.EventKind.KILL_SWITCH,
            {
                'stage': 'fired',
                'reason': reason,
                'until_date': until_date.isoformat(),
                'dry_run': self._mode != 'live',
            },
        )
        try:
            outcome = await self._reader.call(self._flatten)
        except ubi_exceptions.UnifiedBrokerInterfaceError as error:
            _LOGGER.exception('The flatten failed')
            outcome = {
                'error': f'{type(error).__name__}: {error}',
            }
        self._publish(
            event_module.EventKind.KILL_SWITCH,
            {
                'stage': 'flatten_finished',
                'outcome': outcome,
            },
        )
        return outcome

    def _flatten(self) -> dict[str, Any]:
        """Asks UBI to flatten the account. It runs in a worker thread, under the UBI lock.

        Returns:
            dict[str, Any]: UBI's answer.
        """
        account = account_module.Account(
            unified_broker_interface=self._reader.client(),
        )
        return account.flatten(
            confirm=_CONFIRMATION,
            dry_run=self._mode != 'live',
        )

    def _publish(self, kind: event_module.EventKind, payload: dict) -> None:
        """Publishes an event for the whole account.

        Args:
            kind (event_module.EventKind): What happened.
            payload (dict): The details.
        """
        self._event_bus.publish(event_module.Event.now(kind, None, payload))
