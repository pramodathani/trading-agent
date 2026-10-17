"""Checks that the exchange calendar is found and covers this year.

Typical usage example:

  result = MarketCalendarCheck(Path('.../calendars')).run()
"""

import datetime
import zoneinfo
from pathlib import Path

from trading_agent.doctor import doctor_check
from trading_agent.scheduling import market_calendar

_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')


class MarketCalendarCheck(doctor_check.DoctorCheck):
    """Checks the exchange holiday calendar."""

    name = 'Exchange calendar (holidays)'

    def __init__(self, calendar_directory: Path | None):
        """Creates the check.

        Args:
            calendar_directory (Path | None): UBI's calendars folder, or None when none is configured.
        """
        self._calendar_directory = calendar_directory

    def run(self) -> doctor_check.CheckResult:
        """Reads the calendar.

        Returns:
            doctor_check.CheckResult: OK when this year is covered, otherwise a warning, because without it holidays look like trading days to the risk engine and the scheduler.
        """
        if self._calendar_directory is None:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.WARNING,
                'market_calendar_directory is not set in trading_agent.toml, so exchange holidays are treated as trading days.',
            )
        calendar = market_calendar.MarketCalendar(self._calendar_directory)
        today = datetime.datetime.now(_INDIA).date()
        year = today.year
        if year not in calendar.years:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.WARNING,
                f"{self._calendar_directory} has no calendar for {year} (it has {calendar.years or 'none'}), so this year's holidays are treated as trading days.",
            )
        upcoming = []
        day = today
        for _ in range(60):
            day = day + datetime.timedelta(days=1)
            closure = calendar.closure(day)
            if closure is not None and day.weekday() < 5:
                upcoming.append(f'{day:%d %b} {closure.name}')
        return doctor_check.CheckResult(
            doctor_check.CheckStatus.OK,
            f'Covers {", ".join(str(item) for item in calendar.years)}; next NSE holidays: {", ".join(upcoming[:3]) or "none in 60 days"}.',
        )
