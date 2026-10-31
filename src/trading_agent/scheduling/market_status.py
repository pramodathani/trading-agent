"""Describes the market's state in one line, for the context line at the top of every message to a trader.

Traders know the time from that line but not the exchange calendar, so without this a trader planned "Tuesday" when Tuesday was a holiday. The line says whether NSE equities trade today, whether they are open now, the next trading day, and any weekday holiday in the coming week.

Typical usage example:

  text = MarketStatus(calendar, hours).describe(now)
  # 'NSE closed today (weekend); next trading day Mon 19 Oct; holiday ahead: Tue 20 Oct Dussehra'
"""

import datetime
import zoneinfo

from trading_agent.risk import exchange_hours as exchange_hours_module
from trading_agent.scheduling import market_calendar as market_calendar_module

_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')
_SATURDAY = 5
_DAYS_AHEAD = 7


class MarketStatus:
    """Writes the market line."""

    def __init__(
        self,
        calendar: market_calendar_module.MarketCalendar,
        hours: exchange_hours_module.ExchangeHours,
    ):
        """Creates the describer.

        Args:
            calendar (market_calendar_module.MarketCalendar): The exchange calendar.
            hours (exchange_hours_module.ExchangeHours): The trading sessions.
        """
        self._calendar = calendar
        self._hours = hours

    def describe(self, moment: datetime.datetime) -> str:
        """The market's state at a moment.

        Args:
            moment (datetime.datetime): The moment.

        Returns:
            str: Today's state for NSE equities, the next trading day, and holidays in the coming week.
        """
        local = moment.astimezone(_INDIA)
        today = local.date()
        parts = []
        if self._calendar.is_trading_day(today):
            is_open, _ = self._hours.is_open(
                'nse', 'nse_equities', local, 'exchange_hours'
            )
            if is_open:
                parts.append('NSE open now')
            elif local.hour < 12:
                parts.append('NSE trades today, not open yet')
            else:
                parts.append('NSE closed for the day')
        else:
            closure = self._calendar.closure(today)
            if closure is not None and today.weekday() < _SATURDAY:
                parts.append(f'NSE closed today ({closure.name})')
            else:
                parts.append('NSE closed today (weekend)')
        next_day = self._calendar.next_trading_day(today)
        parts.append(f'next trading day {next_day:%a %d %b}')
        holidays = []
        for offset in range(1, _DAYS_AHEAD + 1):
            day = today + datetime.timedelta(days=offset)
            closure = self._calendar.closure(day)
            if (
                closure is not None
                and day.weekday() < _SATURDAY
                and closure.closed == 'all'
            ):
                holidays.append(f'{day:%a %d %b} {closure.name}')
        if holidays:
            parts.append(f'holiday ahead: {", ".join(holidays)}')
        return '; '.join(parts)
