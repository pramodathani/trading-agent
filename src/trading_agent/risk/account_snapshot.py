"""The state of the account that the risk engine needs, read fresh from UBI before each order.

Typical usage example:

  snapshot = await AccountSnapshotReader(broker_reader).read()
  snapshot.net_quantity('f310e1b0-...')
"""

import dataclasses
from typing import Any

from trading_agent.trading import broker_reader as broker_reader_module

_FUNDS_PATH = '/api/portfolio/funds'
_POSITIONS_PATH = '/api/portfolio/positions'
_HOLDINGS_PATH = '/api/portfolio/holdings'


@dataclasses.dataclass(frozen=True)
class PositionRow:
    """One open position, in one instrument and product, merged across brokers.

    Attributes:
        instrument_id: UBI's id for the instrument.
        symbol: The instrument's symbol.
        segment: UBI's segment.
        product: UBI's position product, such as intraday or delivery.
        quantity: Positive when long, negative when short.
        last_price: The latest price.
    """

    instrument_id: str
    symbol: str
    segment: str
    product: str
    quantity: int
    last_price: float


@dataclasses.dataclass(frozen=True)
class AccountSnapshot:
    """Balances, today's profit and loss, and open positions.

    Attributes:
        total_balance: The total balance across every broker: available balance plus margin in use.
        margin_utilized: Margin already blocked across every broker.
        day_pnl: Today's realised plus unrealised profit or loss, negative for a loss.
        positions: The open positions.
        held_quantities: The quantity held as delivery holdings, by instrument id.
        held_symbols: The upper-case symbols of every delivery holding, including holdings UBI gives no instrument id.
    """

    total_balance: float
    margin_utilized: float
    day_pnl: float
    positions: tuple[PositionRow, ...]
    held_quantities: dict[str, int] = dataclasses.field(default_factory=dict)
    held_symbols: frozenset[str] = frozenset()

    def net_quantity(self, instrument_id: str) -> int:
        """The account's total position in one instrument, across products.

        Args:
            instrument_id (str): UBI's id for the instrument.

        Returns:
            int: Positive when long, negative when short, zero when flat.
        """
        total = 0
        for row in self.positions:
            if row.instrument_id == instrument_id:
                total += row.quantity
        return total

    def held_instrument_ids(self) -> set[str]:
        """The instruments with a non-zero position or a holding.

        Returns:
            set[str]: Their ids.
        """
        held = set()
        for row in self.positions:
            if row.quantity != 0:
                held.add(row.instrument_id)
        for instrument_id, quantity in self.held_quantities.items():
            if quantity != 0:
                held.add(instrument_id)
        return held


class AccountSnapshotReader:
    """Reads an AccountSnapshot from UBI."""

    def __init__(self, reader: broker_reader_module.BrokerReader):
        """Creates the reader.

        Args:
            reader (broker_reader_module.BrokerReader): The shared reader of UBI.
        """
        self._reader = reader

    async def read(self) -> AccountSnapshot:
        """Reads funds and positions.

        Returns:
            AccountSnapshot: The account now.

        Raises:
            tradingmachine.unified_broker_interface.exceptions.UnifiedBrokerInterfaceError: UBI could not answer.
        """
        funds = await self._reader.call(self._read_funds)
        positions = await self._reader.call(self._read_positions)
        holdings = await self._reader.call(self._read_holdings)
        summary = funds['summary']
        rows = []
        for row in positions.get('net', []):
            rows.append(self._position_row(row))
        held_quantities = {}
        held_symbols = set()
        for row in holdings.get('holdings', []):
            if row.get('symbol'):
                held_symbols.add(str(row['symbol']).upper())
            instrument_id = row.get('instrument_id')
            if instrument_id:
                held_quantities[str(instrument_id)] = int(
                    row.get('quantity') or 0
                )
        return AccountSnapshot(
            total_balance=float(summary['total_balance']),
            margin_utilized=float(summary.get('margin_utilized') or 0),
            day_pnl=float(positions['summary']['day']['total_pnl']),
            positions=tuple(rows),
            held_quantities=held_quantities,
            held_symbols=frozenset(held_symbols),
        )

    def _read_funds(self) -> dict[str, Any]:
        """Reads the funds. It runs in a worker thread.

        Returns:
            dict[str, Any]: UBI's funds answer.
        """
        return self._reader.get(_FUNDS_PATH)

    def _read_positions(self) -> dict[str, Any]:
        """Reads the positions. It runs in a worker thread.

        Returns:
            dict[str, Any]: UBI's positions answer.
        """
        return self._reader.get(_POSITIONS_PATH)

    def _read_holdings(self) -> dict[str, Any]:
        """Reads the delivery holdings. It runs in a worker thread.

        Returns:
            dict[str, Any]: UBI's holdings answer.
        """
        return self._reader.get(_HOLDINGS_PATH)

    def _position_row(self, row: dict[str, Any]) -> PositionRow:
        """Turns one of UBI's position rows into a PositionRow.

        Args:
            row (dict[str, Any]): The row.

        Returns:
            PositionRow: The position.
        """
        return PositionRow(
            instrument_id=str(row.get('instrument_id') or row.get('symbol')),
            symbol=str(row.get('symbol', '')),
            segment=str(row.get('segment', '')),
            product=str(row.get('product', '')),
            quantity=int(row.get('quantity') or 0),
            last_price=float(row.get('last_price') or 0),
        )
