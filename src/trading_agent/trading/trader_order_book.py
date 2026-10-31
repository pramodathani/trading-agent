"""The record of which trader placed which order, in a small SQLite database shared by every trader.

A trader may change or cancel only the orders it placed itself, and this record is how the order tools know which those are. Each order is kept under its parent_id, the handle UBI's order engine gives every order, and also under its broker order_id once a broker has accepted it. A dry run reaches no broker and gets no id from UBI, so it is kept under a made-up id that starts with "dry-", which lets a trader practise changing and cancelling it.

Typical usage example:

  book = TraderOrderBook(Path('workspace/shared/trader_orders.db'))
  record = book.find('main', parent_id='...', order_id=None)
"""

import dataclasses
import datetime
import sqlite3
import threading
from pathlib import Path

_SCHEMA = 'CREATE TABLE IF NOT EXISTS trader_orders (record_id TEXT PRIMARY KEY, trader TEXT NOT NULL, kind TEXT NOT NULL, parent_id TEXT, order_id TEXT, instrument_id TEXT NOT NULL, exchange TEXT NOT NULL, segment TEXT NOT NULL, symbol TEXT NOT NULL, transaction_type TEXT NOT NULL, quantity INTEGER NOT NULL, product TEXT NOT NULL, price REAL NOT NULL, dry_run INTEGER NOT NULL, state TEXT NOT NULL, placed_at TEXT NOT NULL)'
_COLUMNS = 'record_id, trader, kind, parent_id, order_id, instrument_id, exchange, segment, symbol, transaction_type, quantity, product, price, dry_run, state, placed_at'
OPEN = 'open'
CANCELLED = 'cancelled'


@dataclasses.dataclass(frozen=True)
class OrderRecord:
    """One order a trader placed.

    Attributes:
        record_id: The key of the record: the parent_id, the order_id, or a made-up "dry-" id for a dry run.
        trader: The trader that placed it.
        kind: "order" for a plain order, "bracket" for a bracket order, or "close" for a closing order.
        parent_id: The handle UBI's order engine gave it, or the made-up id for a dry run, or None.
        order_id: The broker's id, or None until a broker has accepted it.
        instrument_id: UBI's id for the instrument.
        exchange: The exchange, such as nse.
        segment: UBI's segment, such as nse_equities.
        symbol: The symbol, or the underlying's for a future or option.
        transaction_type: "buy" or "sell".
        quantity: How many units.
        product: "cnc", "mis" or "nrml".
        price: The price the order was valued at.
        dry_run: Whether it was a dry run that reached no broker.
        state: "open", or "cancelled" once a trader cancelled it.
        placed_at: When it was placed, as ISO text.
    """

    record_id: str
    trader: str
    kind: str
    parent_id: str | None
    order_id: str | None
    instrument_id: str
    exchange: str
    segment: str
    symbol: str
    transaction_type: str
    quantity: int
    product: str
    price: float
    dry_run: bool
    state: str
    placed_at: str


class TraderOrderBook:
    """The table of orders placed by the traders, and the questions the order tools ask of it."""

    def __init__(self, path: Path):
        """Opens the database, creating it and its table if needed.

        Args:
            path (Path): The database file.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._connection:
            self._connection.execute(_SCHEMA)

    def add(self, record: OrderRecord) -> None:
        """Stores a newly placed order.

        Args:
            record (OrderRecord): The order.
        """
        with self._lock, self._connection:
            self._connection.execute(
                f'INSERT OR REPLACE INTO trader_orders ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (
                    record.record_id,
                    record.trader,
                    record.kind,
                    record.parent_id,
                    record.order_id,
                    record.instrument_id,
                    record.exchange,
                    record.segment,
                    record.symbol,
                    record.transaction_type,
                    record.quantity,
                    record.product,
                    record.price,
                    int(record.dry_run),
                    record.state,
                    record.placed_at,
                ),
            )

    def find(
        self,
        trader: str,
        parent_id: str | None,
        order_id: str | None,
    ) -> OrderRecord | None:
        """Finds one of a trader's orders by its parent_id or its order_id.

        Args:
            trader (str): The trader asking; another trader's order is never found.
            parent_id (str | None): The engine's handle, or None.
            order_id (str | None): The broker's id, or None.

        Returns:
            OrderRecord | None: The order, or None when this trader placed no such order.
        """
        with self._lock:
            row = self._connection.execute(
                f'SELECT {_COLUMNS} FROM trader_orders WHERE trader = ? AND ((parent_id IS NOT NULL AND parent_id = ?) OR (order_id IS NOT NULL AND order_id = ?))',
                (trader, parent_id, order_id),
            ).fetchone()
        if row is None:
            return None
        return self._record(row)

    def open_orders(self, trader: str) -> list[OrderRecord]:
        """A trader's orders that it has not cancelled.

        Args:
            trader (str): The trader.

        Returns:
            list[OrderRecord]: The orders, oldest first.
        """
        with self._lock:
            rows = self._connection.execute(
                f'SELECT {_COLUMNS} FROM trader_orders WHERE trader = ? AND state = ? ORDER BY placed_at',
                (trader, OPEN),
            ).fetchall()
        records = []
        for row in rows:
            records.append(self._record(row))
        return records

    def change(self, record_id: str, quantity: int, price: float) -> None:
        """Records a new quantity and price after an order was modified.

        Args:
            record_id (str): The order's record id.
            quantity (int): Its new quantity.
            price (float): Its new valuation price.
        """
        with self._lock, self._connection:
            self._connection.execute(
                'UPDATE trader_orders SET quantity = ?, price = ? WHERE record_id = ?',
                (quantity, price, record_id),
            )

    def mark_cancelled(self, record_id: str) -> None:
        """Records that an order was cancelled.

        Args:
            record_id (str): The order's record id.
        """
        with self._lock, self._connection:
            self._connection.execute(
                'UPDATE trader_orders SET state = ? WHERE record_id = ?',
                (CANCELLED, record_id),
            )

    def close(self) -> None:
        """Closes the database."""
        with self._lock:
            self._connection.close()

    @staticmethod
    def now_text() -> str:
        """The current time in UTC as ISO text, for placed_at.

        Returns:
            str: The time.
        """
        return datetime.datetime.now(datetime.UTC).isoformat()

    def _record(self, row: tuple) -> OrderRecord:
        """Turns a database row into an OrderRecord.

        Args:
            row (tuple): The row, in the order of the table's columns.

        Returns:
            OrderRecord: The record.
        """
        return OrderRecord(
            record_id=row[0],
            trader=row[1],
            kind=row[2],
            parent_id=row[3],
            order_id=row[4],
            instrument_id=row[5],
            exchange=row[6],
            segment=row[7],
            symbol=row[8],
            transaction_type=row[9],
            quantity=int(row[10]),
            product=row[11],
            price=float(row[12]),
            dry_run=bool(row[13]),
            state=row[14],
            placed_at=row[15],
        )
