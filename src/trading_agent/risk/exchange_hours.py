"""Decides whether an exchange is open for new orders at a given moment.

With trading_window = "exchange_hours", each exchange's own regular session applies: NSE and BSE equities and derivatives 09:15 to 15:30, currency derivatives 09:00 to 17:00, and MCX 09:00 to 23:30, or 23:55 while the United States is not on daylight saving time, because MCX's evening follows US trading hours. A fixed "HH:MM-HH:MM" window applies the same hours to every exchange. Weekends are closed. Exchange holidays are not known here yet; the market calendar of milestone 15 adds them.

Typical usage example:

  hours = ExchangeHours()
  is_open, reason = hours.is_open('nse', 'nse_equities', moment, 'exchange_hours')
"""

import datetime
import zoneinfo

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


class ExchangeHours:
    """The regular trading sessions of the Indian exchanges."""

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
        start, end = self._session(exchange, segment, local, trading_window)
        session_text = f'{start:%H:%M}-{end:%H:%M} India time on weekdays'
        if local.weekday() >= _SATURDAY:
            return False, f'it is a weekend; the session is {session_text}'
        if not start <= local.time() < end:
            return (
                False,
                f'it is {local:%H:%M} India time; the session is {session_text}',
            )
        return True, session_text

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
