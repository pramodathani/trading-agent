"""Which days the Indian exchanges trade, read from UBI's own exchange calendar files.

UBI keeps one YAML file a year, generated from the exchanges' own publications (NSE, BSE, MCX and NCDEX), listing each holiday by exchange and calendar and each special session such as Muhurat trading. Reading the same files keeps trading-agent and UBI in agreement about every holiday.

A calendar is a set of segments that close together: `equity` (cash, indices and equity derivatives), `currency` (currency derivatives, which also close on bank holidays) and `commodity`. A commodity holiday can close only the morning or only the evening session.

Typical usage example:

  calendar = MarketCalendar(Path('.../calendars'))
  calendar.is_trading_day(datetime.date(2026, 10, 20))  # False: Dussehra
"""

import dataclasses
import datetime
import logging
from pathlib import Path

import yaml

_LOGGER = logging.getLogger(__name__)
_SATURDAY = 5
_MOST_DAYS_AHEAD = 30
EQUITY = 'equity'
CURRENCY = 'currency'
COMMODITY = 'commodity'


@dataclasses.dataclass(frozen=True)
class Closure:
    """One holiday.

    Attributes:
        name: The holiday's name, as the exchange publishes it.
        closed: "all", or "morning" or "evening" for a commodity calendar.
    """

    name: str
    closed: str


@dataclasses.dataclass(frozen=True)
class SpecialSession:
    """A session on a day that would otherwise be closed, such as Muhurat trading.

    Attributes:
        name: The session's name.
        opens: When it opens, India time.
        closes: When it closes, India time.
    """

    name: str
    opens: datetime.time
    closes: datetime.time


class MarketCalendar:
    """The exchanges' holidays and special sessions."""

    def __init__(self, calendar_directory: Path | None):
        """Reads every year's file in the folder.

        A missing folder or unreadable file is logged; the calendar then knows weekends only, and the doctor reports it.

        Args:
            calendar_directory (Path | None): UBI's calendars folder, or None to know weekends only.
        """
        self._closures: dict[tuple[str, str, datetime.date], Closure] = {}
        self._special_sessions: dict[
            tuple[str, str, datetime.date], SpecialSession
        ] = {}
        self.years: list[int] = []
        if calendar_directory is None or not calendar_directory.is_dir():
            if calendar_directory is not None:
                _LOGGER.warning(
                    'No exchange calendar folder at %s', calendar_directory
                )
            return
        for path in sorted(calendar_directory.glob('*.yaml')):
            try:
                self._read_year(path)
            except OSError, yaml.YAMLError, KeyError, TypeError, ValueError:
                _LOGGER.exception(
                    'Could not read the exchange calendar %s', path
                )

    def calendar_for(self, exchange: str, segment: str) -> str:
        """The calendar an instrument's segment follows.

        Args:
            exchange (str): The exchange, such as nse or mcx.
            segment (str): UBI's segment, such as nse_equities or mcx_commodities.

        Returns:
            str: "equity", "currency" or "commodity".
        """
        text = f'{exchange}_{segment}'.lower()
        if 'commodit' in text or exchange.lower() in ('mcx', 'ncdex'):
            return COMMODITY
        if 'currency' in text or exchange.lower() == 'cds':
            return CURRENCY
        return EQUITY

    def closure(
        self,
        day: datetime.date,
        exchange: str = 'nse',
        calendar: str = EQUITY,
    ) -> Closure | None:
        """The holiday on a day, if there is one.

        Args:
            day (datetime.date): The date.
            exchange (str): The exchange.
            calendar (str): "equity", "currency" or "commodity".

        Returns:
            Closure | None: The holiday, or None.
        """
        return self._closures.get((exchange.lower(), calendar, day))

    def special_session(
        self,
        day: datetime.date,
        exchange: str = 'nse',
        calendar: str = EQUITY,
    ) -> SpecialSession | None:
        """The special session on a day, if there is one.

        Args:
            day (datetime.date): The date.
            exchange (str): The exchange.
            calendar (str): "equity", "currency" or "commodity".

        Returns:
            SpecialSession | None: The session, or None.
        """
        return self._special_sessions.get((exchange.lower(), calendar, day))

    def is_trading_day(
        self,
        day: datetime.date,
        exchange: str = 'nse',
        calendar: str = EQUITY,
    ) -> bool:
        """Says whether any part of a day trades.

        Args:
            day (datetime.date): The date.
            exchange (str): The exchange.
            calendar (str): "equity", "currency" or "commodity".

        Returns:
            bool: True on a weekday that is not a full holiday, or on a day with a special session.
        """
        if self.special_session(day, exchange, calendar) is not None:
            return True
        if day.weekday() >= _SATURDAY:
            return False
        closure = self.closure(day, exchange, calendar)
        return closure is None or closure.closed != 'all'

    def next_trading_day(
        self,
        after: datetime.date,
        exchange: str = 'nse',
        calendar: str = EQUITY,
    ) -> datetime.date:
        """The first trading day after a date.

        Args:
            after (datetime.date): The date to count from, not itself included.
            exchange (str): The exchange.
            calendar (str): "equity", "currency" or "commodity".

        Returns:
            datetime.date: The next trading day.

        Raises:
            ValueError: None of the next thirty days trades, which means the calendar is wrong.
        """
        day = after
        for _ in range(_MOST_DAYS_AHEAD):
            day = day + datetime.timedelta(days=1)
            if self.is_trading_day(day, exchange, calendar):
                return day
        raise ValueError(
            f'No trading day in the {_MOST_DAYS_AHEAD} days after {after}'
        )

    def _read_year(self, path: Path) -> None:
        """Reads one year's file.

        Args:
            path (Path): The YAML file.
        """
        document = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
        for exchange, calendars in (document.get('holidays') or {}).items():
            for calendar, entries in calendars.items():
                for entry in entries or []:
                    day = self._date(entry['date'])
                    self._closures[(exchange, calendar, day)] = Closure(
                        name=str(entry.get('name', 'holiday')),
                        closed=str(entry.get('closed', 'all')),
                    )
        for entry in document.get('special_sessions') or []:
            day = self._date(entry['date'])
            session = SpecialSession(
                name=str(entry.get('name', 'special session')),
                opens=datetime.time.fromisoformat(str(entry['opens'])),
                closes=datetime.time.fromisoformat(str(entry['closes'])),
            )
            for exchange in entry.get('exchanges') or []:
                for calendar in entry.get('calendars') or []:
                    self._special_sessions[(exchange, calendar, day)] = session
        year = document.get('year')
        if isinstance(year, int):
            self.years.append(year)

    def _date(self, value: object) -> datetime.date:
        """Turns a YAML date into a date.

        Args:
            value (object): A date, as YAML reads an unquoted ISO date, or an ISO string.

        Returns:
            datetime.date: The date.
        """
        if isinstance(value, datetime.date):
            return value
        return datetime.date.fromisoformat(str(value))
