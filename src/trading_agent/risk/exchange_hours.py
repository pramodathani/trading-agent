"""Decides whether an exchange is open for new orders at a given moment.

With trading_window = "exchange_hours", each exchange's own regular session applies: NSE and BSE equities and derivatives 09:15 to 15:30, currency derivatives 09:00 to 17:00, and MCX 09:00 to 23:30, or 23:55 while the United States is not on daylight saving time, because MCX's evening follows US trading hours. A fixed "HH:MM-HH:MM" window applies the same hours to every exchange. Weekends are closed. With a market calendar, exchange holidays are closed too, a commodity holiday that closes only the morning or evening session narrows the hours, and a special session such as Muhurat trading opens the exchange for its own hours, even on a weekend or holiday.

Typical usage example:

  hours = ExchangeHours()
  is_open, reason = hours.is_open('nse', 'nse_equities', moment, 'exchange_hours')
"""

import datetime
import zoneinfo

from trading_agent.scheduling import market_calendar as market_calendar_module

_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')
_NEW_YORK = zoneinfo.ZoneInfo('America/New_York')
_EQUITY_SESSION = (
    datetime.time(9, 15),
    datetime.time(15, 30),
)
_CURRENCY_SESSION = (
    datetime.time(9, 0),
    datetime.time(17, 0),
)
_MCX_OPEN = datetime.time(9, 0)
_MCX_CLOSE_DURING_US_DAYLIGHT_SAVING = datetime.time(23, 30)
_MCX_CLOSE_OTHERWISE = datetime.time(23, 55)
_SATURDAY = 5
_COMMODITY_SPLIT = datetime.time(17, 0)
_QUARTER_HOUR = datetime.timedelta(minutes=15)
_SEARCH_LENGTH = datetime.timedelta(days=15)


class ExchangeHours:
    """The trading sessions of the Indian exchanges."""

    def __init__(
        self,
        calendar: market_calendar_module.MarketCalendar | None = None,
    ):
        """Creates the checker.

        Args:
            calendar (market_calendar_module.MarketCalendar | None): The exchanges' holidays and special sessions, or None to know weekends only.
        """
        self._calendar = calendar

    def is_open(
        self,
        exchange: str,
        segment: str,
        moment: datetime.datetime,
        trading_window: str,
    ) -> tuple[bool, str]:
        """Says whether new orders are allowed for an instrument at a moment.

        Args:
            exchange (str): The exchange, such as nse, bse or mcx.
            segment (str): UBI's segment, used to tell currency derivatives apart.
            moment (datetime.datetime): The moment, with a time zone.
            trading_window (str): "exchange_hours", or "HH:MM-HH:MM" in India time.

        Returns:
            tuple[bool, str]: Whether it is open, and the session that applies, for messages.
        """
        local = moment.astimezone(_INDIA)
        special = self._special_session(exchange, segment, local)
        if special is not None:
            special_text = f'the {special.name} session, {special.opens:%H:%M}-{special.closes:%H:%M} India time'
            if special.opens <= local.time() < special.closes:
                return True, special_text
            return (
                False,
                f'it is {local:%H:%M} India time; today has only {special_text}',
            )
        start, end = self._session(exchange, segment, local, trading_window)
        session_text = f'{start:%H:%M}-{end:%H:%M} India time on weekdays'
        if local.weekday() >= _SATURDAY:
            return False, f'it is a weekend; the session is {session_text}'
        closure = self._closure(exchange, segment, local)
        if closure is not None:
            if closure.closed == 'all':
                return (
                    False,
                    f'it is an exchange holiday ({closure.name}); the session is {session_text}',
                )
            if closure.closed == 'morning':
                start = max(start, _COMMODITY_SPLIT)
            if closure.closed == 'evening':
                end = min(end, _COMMODITY_SPLIT)
            session_text = f'{start:%H:%M}-{end:%H:%M} India time today, because of {closure.name}'
        if not start <= local.time() < end:
            return (
                False,
                f'it is {local:%H:%M} India time; the session is {session_text}',
            )
        return True, session_text

    def next_open(
        self,
        exchange: str,
        segment: str,
        moment: datetime.datetime,
        trading_window: str,
    ) -> datetime.datetime:
        """Finds when the exchange next opens after a moment, to the quarter hour.

        Args:
            exchange (str): The exchange, such as nse or mcx.
            segment (str): UBI's segment, such as nse_equities.
            moment (datetime.datetime): The moment to start from, with a time zone.
            trading_window (str): "exchange_hours", or "HH:MM-HH:MM" in India time.

        Returns:
            datetime.datetime: The first quarter hour after the moment, in India time, at which the exchange is open, or the moment itself when the exchange does not open within the next fifteen days.
        """
        local = moment.astimezone(_INDIA)
        candidate = local.replace(second=0, microsecond=0)
        candidate = candidate + _QUARTER_HOUR
        candidate = candidate - datetime.timedelta(
            minutes=candidate.minute % 15
        )
        last_candidate = local + _SEARCH_LENGTH
        while candidate <= last_candidate:
            is_open, _ = self.is_open(
                exchange,
                segment,
                candidate,
                trading_window,
            )
            if is_open:
                return candidate
            candidate = candidate + _QUARTER_HOUR
        return local

    def _special_session(
        self,
        exchange: str,
        segment: str,
        local: datetime.datetime,
    ) -> market_calendar_module.SpecialSession | None:
        """The special session on the moment's date, if the calendar has one.

        Args:
            exchange (str): The exchange.
            segment (str): UBI's segment.
            local (datetime.datetime): The moment in India time.

        Returns:
            market_calendar_module.SpecialSession | None: The session, or None.
        """
        if self._calendar is None:
            return None
        calendar_name = self._calendar.calendar_for(exchange, segment)
        return self._calendar.special_session(
            local.date(), exchange, calendar_name
        )

    def _closure(
        self,
        exchange: str,
        segment: str,
        local: datetime.datetime,
    ) -> market_calendar_module.Closure | None:
        """The holiday on the moment's date, if the calendar has one.

        Args:
            exchange (str): The exchange.
            segment (str): UBI's segment.
            local (datetime.datetime): The moment in India time.

        Returns:
            market_calendar_module.Closure | None: The holiday, or None.
        """
        if self._calendar is None:
            return None
        calendar_name = self._calendar.calendar_for(exchange, segment)
        return self._calendar.closure(local.date(), exchange, calendar_name)

    def _session(
        self,
        exchange: str,
        segment: str,
        local: datetime.datetime,
        trading_window: str,
    ) -> tuple[datetime.time, datetime.time]:
        """The opening and closing times that apply.

        Args:
            exchange (str): The exchange.
            segment (str): UBI's segment.
            local (datetime.datetime): The moment in India time.
            trading_window (str): "exchange_hours", or "HH:MM-HH:MM".

        Returns:
            tuple[datetime.time, datetime.time]: The opening and closing times.
        """
        if trading_window != 'exchange_hours':
            opening_text, closing_text = trading_window.split('-')
            return (
                datetime.time.fromisoformat(opening_text),
                datetime.time.fromisoformat(closing_text),
            )
        if exchange.lower() == 'mcx':
            return _MCX_OPEN, self._mcx_close(local)
        if 'currency' in segment or exchange.lower() == 'cds':
            return _CURRENCY_SESSION
        return _EQUITY_SESSION

    def _mcx_close(self, local: datetime.datetime) -> datetime.time:
        """MCX's closing time, which depends on whether the United States is on daylight saving time.

        Args:
            local (datetime.datetime): The moment in India time.

        Returns:
            datetime.time: 23:30 during US daylight saving time, 23:55 otherwise.
        """
        new_york = local.astimezone(_NEW_YORK)
        if new_york.dst():
            return _MCX_CLOSE_DURING_US_DAYLIGHT_SAVING
        return _MCX_CLOSE_OTHERWISE
