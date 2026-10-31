"""Keeps one trader's price alerts: wake me when this instrument trades above or below a price.

Alerts live in `traders/<trader>/alerts.json`. The market watcher checks them every cycle while the market is open, wakes the trader when one is crossed, and removes it, so each alert fires once.

Typical usage example:

  store = PriceAlertStore(Path('workspace/traders/main/alerts.json'))
  store.add(alert)
"""

import dataclasses
import datetime
import json
import logging
import os
import uuid
import zoneinfo
from pathlib import Path
from typing import Any, Self

_LOGGER = logging.getLogger(__name__)
_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')
ABOVE = 'above'
BELOW = 'below'


@dataclasses.dataclass(frozen=True)
class PriceAlert:
    """One price alert.

    Attributes:
        alert_id: A short identifier.
        instrument_id: UBI's id for the instrument.
        exchange: The instrument's exchange.
        segment: Its segment.
        symbol: Its symbol, for messages.
        condition: "above" or "below".
        price: The price that fires the alert.
        note: What the trader wanted to do when it fires.
        created_at: When it was set, as an ISO 8601 string.
    """

    alert_id: str
    instrument_id: str
    exchange: str
    segment: str
    symbol: str
    condition: str
    price: float
    note: str
    created_at: str

    @classmethod
    def new(cls, **fields: Any) -> Self:
        """Creates an alert with a fresh identifier and creation time.

        Args:
            **fields (Any): The other fields.

        Returns:
            PriceAlert: The alert.
        """
        return cls(
            alert_id=uuid.uuid4().hex[:8],
            created_at=datetime.datetime.now(_INDIA).isoformat(
                timespec='seconds'
            ),
            **fields,
        )

    def is_crossed(self, last_price: float) -> bool:
        """Says whether a price fires the alert.

        Args:
            last_price (float): The latest traded price.

        Returns:
            bool: True when the price is at or beyond the alert's price on its side.
        """
        if self.condition == ABOVE:
            return last_price >= self.price
        return last_price <= self.price

    def describe(self) -> str:
        """The alert in one line.

        Returns:
            str: Such as "INFY above 1,175.00 (sell half)".
        """
        note = f' ({self.note})' if self.note else ''
        return f'{self.symbol} {self.condition} {self.price:,.2f}{note}'


class PriceAlertStore:
    """One trader's alerts file."""

    def __init__(self, path: Path):
        """Describes the file without touching the disk.

        Args:
            path (Path): The trader's alerts.json.
        """
        self._path = path

    def alerts(self) -> list[PriceAlert]:
        """Reads the alerts; a damaged entry is logged and left out.

        Returns:
            list[PriceAlert]: The alerts, oldest first.
        """
        if not self._path.is_file():
            return []
        try:
            entries = json.loads(self._path.read_text(encoding='utf-8'))
        except OSError, ValueError:
            _LOGGER.exception('Could not read %s', self._path)
            return []
        alerts = []
        for entry in entries:
            try:
                alerts.append(PriceAlert(**entry))
            except TypeError:
                _LOGGER.warning('Skipped a damaged alert in %s', self._path)
        return alerts

    def add(self, alert: PriceAlert) -> None:
        """Adds an alert.

        Args:
            alert (PriceAlert): The alert.
        """
        alerts = self.alerts()
        alerts.append(alert)
        self._write(alerts)

    def remove(self, alert_id: str) -> PriceAlert | None:
        """Removes an alert.

        Args:
            alert_id (str): The alert's identifier.

        Returns:
            PriceAlert | None: The removed alert, or None when there was none with that id.
        """
        kept = []
        removed = None
        for alert in self.alerts():
            if alert.alert_id == alert_id:
                removed = alert
            else:
                kept.append(alert)
        if removed is not None:
            self._write(kept)
        return removed

    def _write(self, alerts: list[PriceAlert]) -> None:
        """Writes the file through a temporary file.

        Args:
            alerts (list[PriceAlert]): The alerts.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = []
        for alert in alerts:
            data.append(dataclasses.asdict(alert))
        temporary = self._path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(data, indent=2), encoding='utf-8')
        os.replace(temporary, self._path)
