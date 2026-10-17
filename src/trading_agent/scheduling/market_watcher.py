"""Watches the market for the desks, with no model: fills, price alerts and the account's loss limits.

While NSE equities or MCX trade, every cycle (15 seconds by default) it:

1. reads UBI's order book once and finds the finished broker orders (complete, cancelled, rejected or expired) that belong to a desk's own orders in the desk order book, matched by parent_id or order_id; each desk gets one message listing its updates;
2. reads the last price of every instrument a desk has an alert on, once each, and wakes the desk for each alert crossed, removing the alert;
3. once a minute, asks the risk engine to check the account, so the kill switch fires at the daily or weekly loss limit, and a desk is halted at its own daily loss limit, even when no desk is placing orders; the account's and each desk's profit and loss are then published as an account_status event.

The ids of orders already reported are kept in a small file, so a restart neither repeats a fill nor forgets one that finished while the gateway was down. Dry-run orders reach no broker, so they never appear in the order book and are skipped.

Typical usage example:

  watcher = MarketWatcher(desks, alert_stores, order_book, reader, risk_engine, hours, event_bus, state_file)
  task = asyncio.create_task(watcher.run())
"""

import asyncio
import datetime
import functools
import json
import logging
import os
import zoneinfo
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from tradingmachine.assets import exceptions as instrument_exceptions
from tradingmachine.unified_broker_interface import exceptions as ubi_exceptions

from trading_agent.risk import account_snapshot as account_snapshot_module
from trading_agent.risk import exchange_hours as exchange_hours_module
from trading_agent.risk import risk_engine as risk_engine_module
from trading_agent.runtime import desk_runtime as desk_runtime_module
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.scheduling import (
    price_alert_store as price_alert_store_module,
)
from trading_agent.trading import broker_reader as broker_reader_module
from trading_agent.trading import desk_order_book as desk_order_book_module
from trading_agent.trading import instrument_arguments

_LOGGER = logging.getLogger(__name__)
_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')
_ORDER_BOOK_PATH = '/api/orders/details'
_FINISHED_STATUSES = (
    'COMPLETE',
    'CANCELLED',
    'REJECTED',
    'EXPIRED',
)
_CLOSED_MARKET_SLEEP_SECONDS = 60.0
_REMEMBERED_ORDER_IDS = 5000


class MarketWatcher:
    """The model-free loop that wakes desks when something happens in the market."""

    def __init__(
        self,
        desks: Mapping[str, desk_runtime_module.DeskRuntime],
        alert_stores: Mapping[str, price_alert_store_module.PriceAlertStore],
        order_book: desk_order_book_module.DeskOrderBook,
        reader: broker_reader_module.BrokerReader,
        risk_engine: risk_engine_module.RiskEngine,
        hours: exchange_hours_module.ExchangeHours,
        event_bus: event_bus_module.EventBus,
        state_file: Path,
        interval_seconds: float = 15.0,
        account_check_seconds: float = 60.0,
        clock: Callable[[], datetime.datetime] | None = None,
    ):
        """Creates the watcher.

        Args:
            desks (Mapping[str, desk_runtime_module.DeskRuntime]): The running desks, keyed by name.
            alert_stores (Mapping[str, price_alert_store_module.PriceAlertStore]): Each desk's alerts.
            order_book (desk_order_book_module.DeskOrderBook): Which desk placed which order.
            reader (broker_reader_module.BrokerReader): The shared UBI reader.
            risk_engine (risk_engine_module.RiskEngine): Checks the account's loss limits.
            hours (exchange_hours_module.ExchangeHours): Decides when the market is open.
            event_bus (event_bus_module.EventBus): Where fills and alerts are published.
            state_file (Path): Where the ids of reported orders are kept.
            interval_seconds (float): The time between cycles while the market is open.
            account_check_seconds (float): The time between account checks.
            clock (Callable[[], datetime.datetime] | None): Returns the current time; None uses the system clock.
        """
        self._desks = desks
        self._alert_stores = alert_stores
        self._order_book = order_book
        self._reader = reader
        self._risk_engine = risk_engine
        self._hours = hours
        self._event_bus = event_bus
        self._state_file = state_file
        self._interval_seconds = interval_seconds
        self._account_check_seconds = account_check_seconds
        self._clock = clock
        self._last_account_check: datetime.datetime | None = None
        self._reported_order_ids = self._read_reported_order_ids()

    async def run(self) -> None:
        """Runs a cycle whenever the market is open, until cancelled."""
        while True:
            now = self._now()
            if not self.market_open(now):
                await asyncio.sleep(_CLOSED_MARKET_SLEEP_SECONDS)
                continue
            try:
                await self.cycle(now)
            except Exception:
                _LOGGER.exception('A market watcher cycle failed')
            await asyncio.sleep(self._interval_seconds)

    def market_open(self, moment: datetime.datetime) -> bool:
        """Says whether NSE equities or MCX trade at a moment.

        Args:
            moment (datetime.datetime): The moment.

        Returns:
            bool: True when either is open.
        """
        nse_open, _ = self._hours.is_open(
            'nse', 'nse_equities', moment, 'exchange_hours'
        )
        mcx_open, _ = self._hours.is_open(
            'mcx', 'mcx_commodities', moment, 'exchange_hours'
        )
        return nse_open or mcx_open

    async def cycle(self, now: datetime.datetime) -> None:
        """Checks fills, alerts and, when due, the account.

        Args:
            now (datetime.datetime): The current time.
        """
        await self.check_fills()
        await self.check_alerts()
        due = (
            self._last_account_check is None
            or (now - self._last_account_check).total_seconds()
            >= self._account_check_seconds
        )
        if due:
            self._last_account_check = now
            snapshot = await self._risk_engine.check_account()
            if snapshot is not None:
                self._publish_account_status(snapshot)

    def _publish_account_status(
        self,
        snapshot: account_snapshot_module.AccountSnapshot,
    ) -> None:
        """Publishes the account's and each desk's profit and loss today.

        Args:
            snapshot (account_snapshot_module.AccountSnapshot): The account now.
        """
        desk_pnl = self._risk_engine.desk_day_pnl(snapshot)
        self._event_bus.publish(
            event_module.Event.now(
                event_module.EventKind.ACCOUNT_STATUS,
                None,
                {
                    'total_balance': snapshot.total_balance,
                    'day_pnl': snapshot.day_pnl,
                    'desk_pnl': desk_pnl,
                    'open_positions': len(snapshot.positions),
                },
            )
        )

    async def check_fills(self) -> int:
        """Reports newly finished broker orders to the desks that placed them.

        Returns:
            int: How many order updates were reported.
        """
        records = []
        for desk_name in self._desks:
            for record in self._order_book.open_orders(desk_name):
                if not record.dry_run:
                    records.append(record)
        if not records:
            return 0
        try:
            book = await self._reader.call(
                functools.partial(self._reader.get, _ORDER_BOOK_PATH)
            )
        except ubi_exceptions.UnifiedBrokerInterfaceError as error:
            _LOGGER.warning('The order book could not be read: %s', error)
            return 0
        updates: dict[str, list[str]] = {}
        orders = []
        if isinstance(book, dict):
            orders = book.get('orders') or []
        for entry in orders:
            order_id = str(entry.get('order_id', ''))
            status = str(entry.get('status') or '').upper()
            if (
                status not in _FINISHED_STATUSES
                or order_id in self._reported_order_ids
            ):
                continue
            record = self._matching_record(entry, records)
            if record is None:
                continue
            self._reported_order_ids.append(order_id)
            line = self._fill_line(entry, record, status)
            updates.setdefault(record.desk, []).append(line)
            self._publish(
                event_module.EventKind.FILL,
                record.desk,
                {
                    'order_id': order_id,
                    'parent_id': record.parent_id,
                    'record_id': record.record_id,
                    'status': status,
                    'filled_quantity': entry.get('filled_quantity'),
                    'average_price': entry.get('average_price'),
                    'message': entry.get('status_message'),
                },
            )
        if updates:
            self._write_reported_order_ids()
        for desk_name, lines in updates.items():
            self._wake(
                desk_name, '[Order update from the market watcher]', lines
            )
        return sum(len(lines) for lines in updates.values())

    async def check_alerts(self) -> int:
        """Wakes desks whose price alerts were crossed, and removes those alerts.

        Returns:
            int: How many alerts fired.
        """
        prices: dict[str, float | None] = {}
        fired = 0
        for desk_name, store in self._alert_stores.items():
            lines = []
            for alert in store.alerts():
                if alert.instrument_id not in prices:
                    prices[alert.instrument_id] = await self._last_price(
                        alert.instrument_id
                    )
                last_price = prices[alert.instrument_id]
                if last_price is None or not alert.is_crossed(last_price):
                    continue
                store.remove(alert.alert_id)
                fired += 1
                note = f' Your note: {alert.note}' if alert.note else ''
                lines.append(
                    f'- {alert.symbol} traded at {last_price:,.2f}, {alert.condition} your alert at {alert.price:,.2f}.{note}'
                )
                self._publish(
                    event_module.EventKind.PRICE_ALERT,
                    desk_name,
                    {
                        'alert_id': alert.alert_id,
                        'symbol': alert.symbol,
                        'condition': alert.condition,
                        'price': alert.price,
                        'last_price': last_price,
                        'note': alert.note,
                    },
                )
            if lines:
                self._wake(
                    desk_name, '[Price alert from the market watcher]', lines
                )
        return fired

    async def _last_price(self, instrument_id: str) -> float | None:
        """Reads an instrument's last traded price.

        Args:
            instrument_id (str): UBI's id.

        Returns:
            float | None: The price, or None when it cannot be read.
        """
        arguments = instrument_arguments.InstrumentArguments(
            instrument_id=instrument_id
        )
        try:
            return await self._reader.call(
                functools.partial(self._read_last_price, arguments)
            )
        except (
            ubi_exceptions.UnifiedBrokerInterfaceError,
            instrument_exceptions.InstrumentError,
        ) as error:
            _LOGGER.warning('No price for %s: %s', instrument_id, error)
            return None

    def _read_last_price(
        self,
        arguments: instrument_arguments.InstrumentArguments,
    ) -> float | None:
        """Does the UBI work for one price. It runs in a worker thread, under the UBI lock.

        Args:
            arguments (instrument_arguments.InstrumentArguments): The instrument.

        Returns:
            float | None: The last traded price.
        """
        return self._reader.tradeable_instrument(arguments).last_price

    def _matching_record(
        self,
        entry: dict[str, Any],
        records: list[desk_order_book_module.OrderRecord],
    ) -> desk_order_book_module.OrderRecord | None:
        """Finds the desk order a broker order belongs to.

        Args:
            entry (dict[str, Any]): One order from UBI's order book.
            records (list[desk_order_book_module.OrderRecord]): The desks' open, real orders.

        Returns:
            desk_order_book_module.OrderRecord | None: The matching record, or None when no desk placed it.
        """
        parent_id = entry.get('engine_parent_id')
        order_id = str(entry.get('order_id', ''))
        for record in records:
            if record.parent_id and record.parent_id == parent_id:
                return record
            if record.order_id and str(record.order_id) == order_id:
                return record
        return None

    def _fill_line(
        self,
        entry: dict[str, Any],
        record: desk_order_book_module.OrderRecord,
        status: str,
    ) -> str:
        """Describes one finished order for the desk.

        Args:
            entry (dict[str, Any]): The broker order.
            record (desk_order_book_module.OrderRecord): The desk's order it belongs to.
            status (str): The finished status.

        Returns:
            str: One line.
        """
        parts = [
            f'- Order {entry.get("order_id")} of your {record.kind} {record.transaction_type} {record.quantity} {record.symbol} (parent_id {record.parent_id}): {status}',
        ]
        if entry.get('filled_quantity'):
            parts.append(
                f', {entry.get("filled_quantity")} filled at an average of {entry.get("average_price")}'
            )
        if entry.get('status_message') and status != 'COMPLETE':
            parts.append(f' ({entry.get("status_message")})')
        return ''.join(parts) + '.'

    def _wake(self, desk_name: str, heading: str, lines: list[str]) -> None:
        """Puts one market-watcher message in a desk's queue.

        Args:
            desk_name (str): The desk.
            heading (str): The message's first line.
            lines (list[str]): One line per update.
        """
        desk = self._desks.get(desk_name)
        if desk is None:
            return
        desk.submit(
            trigger_module.Trigger.now(
                trigger_module.TriggerSource.MARKET_WATCHER,
                desk_name,
                '\n'.join([heading, *lines]),
            )
        )

    def _read_reported_order_ids(self) -> list[str]:
        """Reads the ids of orders already reported.

        Returns:
            list[str]: The ids, oldest first.
        """
        if not self._state_file.is_file():
            return []
        try:
            data = json.loads(self._state_file.read_text(encoding='utf-8'))
        except OSError, ValueError:
            _LOGGER.exception('Could not read %s', self._state_file)
            return []
        return [
            str(order_id) for order_id in data.get('reported_order_ids', [])
        ]

    def _write_reported_order_ids(self) -> None:
        """Writes the ids of orders already reported, keeping the most recent 5,000."""
        self._reported_order_ids = self._reported_order_ids[
            -_REMEMBERED_ORDER_IDS:
        ]
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._state_file.with_suffix('.json.tmp')
        temporary.write_text(
            json.dumps(
                {
                    'reported_order_ids': self._reported_order_ids,
                }
            ),
            encoding='utf-8',
        )
        os.replace(temporary, self._state_file)

    def _now(self) -> datetime.datetime:
        """The current time in India.

        Returns:
            datetime.datetime: The time.
        """
        if self._clock is not None:
            return self._clock()
        return datetime.datetime.now(_INDIA)

    def _publish(
        self,
        kind: event_module.EventKind,
        desk_name: str,
        payload: dict,
    ) -> None:
        """Publishes an event for a desk.

        Args:
            kind (event_module.EventKind): What happened.
            desk_name (str): The desk.
            payload (dict): The details.
        """
        self._event_bus.publish(
            event_module.Event.now(kind, desk_name, payload)
        )
