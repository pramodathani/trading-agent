"""The risk engine's memory, in a small SQLite database shared by every trader.

It records which trader owns which instrument, which trader owned each instrument on each day (so a trader's profit and loss can be worked out even after it closed a position and gave the instrument up), when each trader's approved orders were sent, each day's profit or loss, and any trading halts, so that all of them survive a restart of the gateway. Only the risk engine and the kill switch write to it; the traders have no tool that can.

Typical usage example:

  ledger = RiskLedger(Path('workspace/shared/risk_ledger.db'))
  owner = ledger.owner(instrument_id)
"""

import datetime
import sqlite3
import threading
from pathlib import Path

_SCHEMA = [
    'CREATE TABLE IF NOT EXISTS ownership (instrument_id TEXT PRIMARY KEY, trader TEXT NOT NULL, claimed_at TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS approvals (trader TEXT NOT NULL, approved_at TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS daily_pnl (trading_date TEXT PRIMARY KEY, pnl REAL NOT NULL)',
    'CREATE TABLE IF NOT EXISTS halts (scope TEXT NOT NULL, reason TEXT NOT NULL, until_date TEXT NOT NULL, created_at TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS day_owners (trading_date TEXT NOT NULL, instrument_id TEXT NOT NULL, trader TEXT NOT NULL, PRIMARY KEY (trading_date, instrument_id))',
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
        """The trader that owns an instrument.

        Args:
            instrument_id (str): The instrument.

        Returns:
            str | None: The trader's name, or None when no trader owns it.
        """
        with self._lock:
            row = self._connection.execute(
                'SELECT trader FROM ownership WHERE instrument_id = ?',
                (instrument_id,),
            ).fetchone()
        if row is None:
            return None
        return row[0]

    def claim(
        self, instrument_id: str, trader: str, now: datetime.datetime
    ) -> None:
        """Gives an instrument to a trader, or renews the trader's claim.

        Args:
            instrument_id (str): The instrument.
            trader (str): The trader.
            now (datetime.datetime): When the claim is made.
        """
        with self._lock, self._connection:
            self._connection.execute(
                'INSERT INTO ownership (instrument_id, trader, claimed_at) VALUES (?, ?, ?) ON CONFLICT(instrument_id) DO UPDATE SET trader = excluded.trader, claimed_at = excluded.claimed_at',
                (instrument_id, trader, now.isoformat()),
            )
            self._connection.execute(
                'INSERT INTO day_owners (trading_date, instrument_id, trader) VALUES (?, ?, ?) ON CONFLICT(trading_date, instrument_id) DO UPDATE SET trader = excluded.trader',
                (now.date().isoformat(), instrument_id, trader),
            )

    def release_unheld(
        self,
        held_instrument_ids: set[str],
        now: datetime.datetime,
        grace: datetime.timedelta,
    ) -> list[str]:
        """Releases claims on instruments that are no longer held.

        A claim younger than the grace period is kept even when nothing is held yet, because the trader's order may still be waiting to fill.

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

    def release(self, instrument_id: str, trader: str) -> bool:
        """Releases a trader's claim on an instrument, leaving another trader's claim alone.

        Args:
            instrument_id (str): The instrument.
            trader (str): The trader giving the claim up.

        Returns:
            bool: True when the trader had the claim and it was released.
        """
        with self._lock, self._connection:
            cursor = self._connection.execute(
                'DELETE FROM ownership WHERE instrument_id = ? AND trader = ?',
                (instrument_id, trader),
            )
        return cursor.rowcount > 0

    def day_owners(self, trading_date: datetime.date) -> dict[str, str]:
        """Which trader owned each instrument on a day, released or not.

        Args:
            trading_date (datetime.date): The India date.

        Returns:
            dict[str, str]: Trader names keyed by instrument id; the last trader to claim an instrument that day.
        """
        with self._lock:
            rows = self._connection.execute(
                'SELECT instrument_id, trader FROM day_owners WHERE trading_date = ?',
                (trading_date.isoformat(),),
            ).fetchall()
        owners = {}
        for instrument_id, trader in rows:
            owners[instrument_id] = trader
        return owners

    def owned_by(self, trader: str) -> set[str]:
        """The instruments a trader owns.

        Args:
            trader (str): The trader.

        Returns:
            set[str]: Their ids.
        """
        with self._lock:
            rows = self._connection.execute(
                'SELECT instrument_id FROM ownership WHERE trader = ?',
                (trader,),
            ).fetchall()
        return {row[0] for row in rows}

    def record_approval(self, trader: str, now: datetime.datetime) -> None:
        """Records that one of a trader's orders was approved.

        Args:
            trader (str): The trader.
            now (datetime.datetime): When.
        """
        with self._lock, self._connection:
            self._connection.execute(
                'INSERT INTO approvals (trader, approved_at) VALUES (?, ?)',
                (trader, now.isoformat()),
            )

    def approvals_since(self, trader: str, since: datetime.datetime) -> int:
        """How many of a trader's orders were approved since a moment.

        Args:
            trader (str): The trader.
            since (datetime.datetime): The start of the period.

        Returns:
            int: The count.
        """
        with self._lock:
            row = self._connection.execute(
                'SELECT COUNT(*) FROM approvals WHERE trader = ? AND approved_at >= ?',
                (trader, since.isoformat()),
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
        """Stops a trader, or the whole account, from opening positions until a date.

        Args:
            scope (str): ACCOUNT_SCOPE, or a trader's name.
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
            scope (str): ACCOUNT_SCOPE, or a trader's name.
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

    def owners(self) -> dict[str, str]:
        """Every instrument a trader owns now.

        Returns:
            dict[str, str]: Trader names keyed by instrument id.
        """
        with self._lock:
            rows = self._connection.execute(
                'SELECT instrument_id, trader FROM ownership'
            ).fetchall()
        owners = {}
        for instrument_id, trader in rows:
            owners[instrument_id] = trader
        return owners

    def halts_in_force(self, today: datetime.date) -> list[dict[str, str]]:
        """Every halt still in force, the account's and the traders'.

        Args:
            today (datetime.date): Today, in India time.

        Returns:
            list[dict[str, str]]: Each halt's scope, reason and the first day trading is allowed again, newest first.
        """
        with self._lock:
            rows = self._connection.execute(
                'SELECT scope, reason, until_date FROM halts WHERE until_date > ? ORDER BY created_at DESC',
                (today.isoformat(),),
            ).fetchall()
        halts = []
        for scope, reason, until_date in rows:
            halts.append(
                {
                    'scope': scope,
                    'reason': reason,
                    'until_date': until_date,
                }
            )
        return halts

    def close(self) -> None:
        """Closes the database."""
        with self._lock:
            self._connection.close()
