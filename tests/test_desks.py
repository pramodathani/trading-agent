"""Tests for running several desks: personas, routines, prompts and per-instrument profit and loss."""

import asyncio
import datetime
import zoneinfo
from pathlib import Path
from typing import Any

from trading_agent.agent import prompt_builder
from trading_agent.risk import account_snapshot
from trading_agent.risk import exchange_hours
from trading_agent.scheduling import built_in_jobs
from trading_agent.scheduling import market_calendar
from trading_agent.scheduling import market_status
from trading_agent.workspace import workspace_layout


class _FakeReader:
    """Answers the three portfolio routes with fixed documents."""

    async def call(self, work: Any) -> Any:
        """Runs the work at once.

        Args:
            work (Any): The callable.

        Returns:
            Any: Its result.
        """
        return work()

    def get(self, path: str, parameters: dict | None = None) -> dict[str, Any]:
        """Returns a fixed document for each portfolio route.

        Args:
            path (str): The route.
            parameters (dict | None): Ignored.

        Returns:
            dict[str, Any]: The document.
        """
        del parameters
        if path.endswith('funds'):
            return {
                'summary': {
                    'total_balance': 100000.0,
                },
            }
        if path.endswith('holdings'):
            return {
                'holdings': [],
            }
        return {
            'net': [],
            'day': [
                {
                    'instrument_id': 'idea',
                    'pnl': {
                        'realized': -300.0,
                        'unrealized': 0.0,
                        'total': -300.0,
                    },
                },
                {
                    'instrument_id': 'tcs',
                    'pnl': {
                        'realized': 50.0,
                        'unrealized': 25.0,
                    },
                },
            ],
            'summary': {
                'day': {
                    'total_pnl': -225.0,
                },
            },
        }


class TestDesks:
    """Each starter desk gets its own persona, routine and view of the others."""

    def test_starter_desks_get_their_own_personas(self, tmp_path: Path) -> None:
        """intraday, scalper and positional get their personas; another desk gets the general template.

        Args:
            tmp_path (Path): A scratch folder.
        """
        layout = workspace_layout.WorkspaceLayout(tmp_path)
        layout.create_missing(
            [
                'intraday',
                'scalper',
                'positional',
                'main',
            ]
        )
        assert (
            layout.persona_file('intraday')
            .read_text(encoding='utf-8')
            .startswith('# Persona.md: the intraday desk')
        )
        assert 'Two layers' in layout.persona_file('scalper').read_text(
            encoding='utf-8'
        )
        assert '`cnc`' in layout.persona_file('positional').read_text(
            encoding='utf-8'
        )
        assert layout.is_template(layout.persona_file('main'))

    def test_scheduled_checks_become_built_in_jobs(self) -> None:
        """Two check times make two jobs named by their time."""
        jobs = built_in_jobs.BuiltInJobs().jobs(
            None, '15:45', ['09:05', '15:05']
        )
        checks = [job for job in jobs if job.job_id.startswith('check-')]
        assert [job.job_id for job in checks] == [
            'check-0905',
            'check-1505',
        ]
        assert checks[0].schedule == '5 9 * * *'
        assert checks[0].text.startswith('[Scheduled check at 09:05]')

    def test_prompt_names_the_other_desks(self, tmp_path: Path) -> None:
        """The scalper's prompt names the others and the one-desk-per-instrument rule.

        Args:
            tmp_path (Path): A scratch folder.
        """
        layout = workspace_layout.WorkspaceLayout(tmp_path)
        layout.create_missing(
            [
                'scalper',
            ]
        )
        text = (
            prompt_builder.PromptBuilder(
                layout,
                'scalper',
                'dry_run',
                other_desks=[
                    'intraday',
                    'positional',
                ],
            )
            .build()
            .text
        )
        assert (
            'Other desks share the same broker account: intraday, positional.'
            in text
        )


class TestDayProfitAndLoss:
    """The account snapshot reads each position's profit and loss from UBI's day view."""

    def test_day_view_is_read_per_instrument(self) -> None:
        """A total is used when given; otherwise realized plus unrealized."""
        snapshot = asyncio.run(
            account_snapshot.AccountSnapshotReader(_FakeReader()).read()
        )
        assert snapshot.day_pnl == -225.0
        assert snapshot.day_pnl_by_instrument == {
            'idea': -300.0,
            'tcs': 75.0,
        }


class TestMarketStatus:
    """The context line's market part knows weekends, holidays and the next trading day."""

    def test_holiday_and_next_trading_day(self, tmp_path: Path) -> None:
        """On Saturday the line names Monday and the Tuesday holiday; on Monday afternoon it names Wednesday.

        Args:
            tmp_path (Path): A scratch folder.
        """
        folder = tmp_path / 'calendars'
        folder.mkdir()
        (folder / '2026.yaml').write_text(
            'year: 2026\nholidays:\n  nse:\n    equity:\n      - {date: 2026-10-20, closed: all, name: "Dussehra"}\n',
            encoding='utf-8',
        )
        calendar = market_calendar.MarketCalendar(folder)
        status = market_status.MarketStatus(
            calendar, exchange_hours.ExchangeHours(calendar)
        )
        india = zoneinfo.ZoneInfo('Asia/Kolkata')
        assert status.describe(
            datetime.datetime(2026, 10, 17, 12, 0, tzinfo=india)
        ) == (
            'NSE closed today (weekend); next trading day Mon 19 Oct; holiday ahead: Tue 20 Oct Dussehra'
        )
        assert status.describe(
            datetime.datetime(2026, 10, 19, 16, 0, tzinfo=india)
        ) == (
            'NSE closed for the day; next trading day Wed 21 Oct; holiday ahead: Tue 20 Oct Dussehra'
        )
