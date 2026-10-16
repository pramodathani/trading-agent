"""The risk engine's memory, in a small SQLite database shared by every desk.

It records which desk owns which instrument, when each desk's approved orders were sent, each day's profit or loss, and any trading halts, so that all of them survive a restart of the gateway. Only the risk engine and the kill switch write to it; the desks have no tool that can.

Typical usage example:

  ledger = RiskLedger(Path('workspace/shared/risk_ledger.db'))
  owner = ledger.owner(instrument_id)
"""

import datetime
import sqlite3
import threading
from pathlib import Path

_SCHEMA = [
    'CREATE TABLE IF NOT EXISTS ownership (instrument_id TEXT PRIMARY KEY, desk TEXT NOT NULL, claimed_at TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS approvals (desk TEXT NOT NULL, approved_at TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS daily_pnl (trading_date TEXT PRIMARY KEY, pnl REAL NOT NULL)',
    'CREATE TABLE IF NOT EXISTS halts (scope TEXT NOT NULL, reason TEXT NOT NULL, until_date TEXT NOT NULL, created_at TEXT NOT NULL)',
]
ACCOUNT_SCOPE = 'account'


class RiskLedger:
    """The ledger's tables and the questions the risk engine asks of them."""

    def __init__(self, path: Path):
        """Opens the database, creating it and its tables if needed.

        Args:
            path (Path): The database file.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._connection:
            for statement in _SCHEMA:
                self._connection.execute(statement)

    def owner(self, instrument_id: str) -> str | None:
        """The desk that owns an instrument.

        Args:
            instrument_id (str): The instrument.

        Returns:
            str | None: The desk's name, or None when no desk owns it.
        """
        with self._lock:
            row = self._connection.execute(
                'SELECT desk FROM ownership WHERE instrument_id = ?',
                (instrument_id,),
            ).fetchone()
        if row is None:
            return None
        return row[0]

    def claim(
        self, instrument_id: str, desk: str, now: datetime.datetime
    ) -> None:
        """Gives an instrument to a desk, or renews the desk's claim.

        Args:
            instrument_id (str): The instrument.
            desk (str): The desk.
            now (datetime.datetime): When the claim is made.
        """
        with self._lock, self._connection:
            self._connection.execute(
                'INSERT INTO ownership (instrument_id, desk, claimed_at) VALUES (?, ?, ?) ON CONFLICT(instrument_id) DO UPDATE SET desk = excluded.desk, claimed_at = excluded.claimed_at',
                (instrument_id, desk, now.isoformat()),
            )

    def release_unheld(
        self,
        held_instrument_ids: set[str],
        now: datetime.datetime,
        grace: datetime.timedelta,
    ) -> list[str]:
        """Releases claims on instruments that are no longer held.

        A claim younger than the grace period is kept even when nothing is held yet, because the desk's order may still be waiting to fill.

        Args:
            held_instrument_ids (set[str]): The instruments the account holds now.
            now (datetime.datetime): The current time.
            grace (datetime.timedelta): How long a claim is kept without a position.

        Returns:
            list[str]: The instruments released.
        """
        released = []
        with self._lock, self._connection:
            rows = self._connection.execute(
                'SELECT instrument_id, claimed_at FROM ownership'
            ).fetchall()
            for instrument_id, claimed_at in rows:
                if instrument_id in held_instrument_ids:
                    continue
                if now - datetime.datetime.fromisoformat(claimed_at) < grace:
                    continue
                self._connection.execute(
                    'DELETE FROM ownership WHERE instrument_id = ?',
                    (instrument_id,),
                )
                released.append(instrument_id)
        return released

    def owned_by(self, desk: str) -> set[str]:
        """The instruments a desk owns.

        Args:
            desk (str): The desk.

        Returns:
            set[str]: Their ids.
        """
        with self._lock:
            rows = self._connection.execute(
                'SELECT instrument_id FROM ownership WHERE desk = ?',
                (desk,),
            ).fetchall()
        return {row[0] for row in rows}

    def record_approval(self, desk: str, now: datetime.datetime) -> None:
        """Records that one of a desk's orders was approved.

        Args:
            desk (str): The desk.
            now (datetime.datetime): When.
        """
        with self._lock, self._connection:
            self._connection.execute(
                'INSERT INTO approvals (desk, approved_at) VALUES (?, ?)',
                (desk, now.isoformat()),
            )

    def approvals_since(self, desk: str, since: datetime.datetime) -> int:
        """How many of a desk's orders were approved since a moment.

        Args:
            desk (str): The desk.
            since (datetime.datetime): The start of the period.

        Returns:
            int: The count.
        """
        with self._lock:
            row = self._connection.execute(
                'SELECT COUNT(*) FROM approvals WHERE desk = ? AND approved_at >= ?',
                (desk, since.isoformat()),
            ).fetchone()
        return int(row[0])

    def record_day_pnl(self, trading_date: datetime.date, pnl: float) -> None:
        """Stores the latest profit or loss seen for a day, replacing any earlier figure.

        Args:
            trading_date (datetime.date): The day, in India time.
            pnl (float): The profit or loss, negative for a loss.
        """
        with self._lock, self._connection:
            self._connection.execute(
                'INSERT INTO daily_pnl (trading_date, pnl) VALUES (?, ?) ON CONFLICT(trading_date) DO UPDATE SET pnl = excluded.pnl',
                (trading_date.isoformat(), pnl),
            )

    def week_pnl(self, trading_date: datetime.date) -> float:
        """The total profit or loss recorded from Monday of a date's week up to that date.

        Args:
            trading_date (datetime.date): A day of the week.

        Returns:
            float: The total, negative for a loss.
        """
        monday = trading_date - datetime.timedelta(days=trading_date.weekday())
        with self._lock:
            row = self._connection.execute(
                'SELECT COALESCE(SUM(pnl), 0) FROM daily_pnl WHERE trading_date >= ? AND trading_date <= ?',
                (monday.isoformat(), trading_date.isoformat()),
            ).fetchone()
        return float(row[0])

    def halt(
        self,
        scope: str,
        reason: str,
        until_date: datetime.date,
        now: datetime.datetime,
    ) -> None:
        """Stops a desk, or the whole account, from opening positions until a date.

        Args:
            scope (str): ACCOUNT_SCOPE, or a desk's name.
            reason (str): Why.
            until_date (datetime.date): The first day trading is allowed again.
            now (datetime.datetime): When the halt starts.
        """
        with self._lock, self._connection:
            self._connection.execute(
                'INSERT INTO halts (scope, reason, until_date, created_at) VALUES (?, ?, ?, ?)',
                (scope, reason, until_date.isoformat(), now.isoformat()),
            )

    def active_halt(self, scope: str, today: datetime.date) -> str | None:
        """The reason for a halt that is still in force.

        Args:
            scope (str): ACCOUNT_SCOPE, or a desk's name.
            today (datetime.date): Today, in India time.

        Returns:
            str | None: The newest halt's reason, or None when no halt applies today.
        """
        with self._lock:
            row = self._connection.execute(
                'SELECT reason FROM halts WHERE scope = ? AND until_date > ? ORDER BY created_at DESC LIMIT 1',
                (scope, today.isoformat()),
            ).fetchone()
        if row is None:
            return None
        return row[0]

    def close(self) -> None:
        """Closes the database."""
        with self._lock:
            self._connection.close()
