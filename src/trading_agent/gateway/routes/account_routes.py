"""Routes for the account: balances, positions, profit and loss, orders, ownership, halts and the kill switch.

  GET  /api/account                the account now, each trader's profit and loss, ownership and halts
  GET  /api/orders?kind=orders     UBI's order book: orders, trades or open_parents
  GET  /api/trader-orders            each trader's open orders in the trader order book
  POST /api/account/kill           halt every trader and flatten the account; needs {"confirm": "FLATTEN"}

Typical usage example:

  application.include_router(AccountRoutes(guard, shared, trader_names).router())
"""

import dataclasses
import datetime
import functools
import zoneinfo
from collections.abc import Callable, Collection
from typing import Any, Literal

import fastapi
import pydantic
from tradingmachine.unified_broker_interface import exceptions as ubi_exceptions

from trading_agent.gateway import access_guard
from trading_agent.gateway import gateway_parts
from trading_agent.gateway.routes import route_group

_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')
_ORDER_BOOK_PATHS = {
    'orders': '/api/orders/details',
    'trades': '/api/orders/trades',
    'open_parents': '/api/orders/parents',
}
_CONFIRMATION = 'FLATTEN'


class KillRequest(pydantic.BaseModel):
    """The body of a kill-switch request.

    Attributes:
        confirm: Must be exactly FLATTEN, so the switch cannot fire by accident.
        reason: Why, for the ledger and the journal.
    """

    confirm: str
    reason: str = pydantic.Field(min_length=1)


class AccountRoutes(route_group.RouteGroup):
    """The account routes."""

    def __init__(
        self,
        guard: access_guard.AccessGuard,
        shared: gateway_parts.SharedParts,
        trader_names: Collection[str],
        clock: Callable[[], datetime.datetime] | None = None,
    ):
        """Creates the routes.

        Args:
            guard (access_guard.AccessGuard): Checks the access token.
            shared (gateway_parts.SharedParts): The shared parts.
            trader_names (Collection[str]): The traders, for their order lists. Read afresh on every request, so the gateway passes its live dictionary of traders and a trader created later is included.
            clock (Callable[[], datetime.datetime] | None): Returns the current time; None uses the system clock.
        """
        super().__init__(guard)
        self._shared = shared
        self._trader_names = trader_names
        self._clock = clock

    def _add_routes(self, router: fastapi.APIRouter) -> None:
        """Adds the account routes.

        Args:
            router (fastapi.APIRouter): The router.
        """
        router.add_api_route('/api/account', self.account, methods=['GET'])
        router.add_api_route('/api/orders', self.orders, methods=['GET'])
        router.add_api_route(
            '/api/trader-orders', self.trader_orders, methods=['GET']
        )
        router.add_api_route('/api/account/kill', self.kill, methods=['POST'])

    async def account(self) -> dict[str, Any]:
        """The account now.

        Returns:
            dict[str, Any]: Balance, margin, today's and this week's profit and loss, each trader's profit and loss, positions, ownership and halts.

        Raises:
            fastapi.HTTPException: UBI cannot be read (status 503).
        """
        try:
            snapshot = await self._shared.snapshot_reader.read()
        except ubi_exceptions.UnifiedBrokerInterfaceError as error:
            raise fastapi.HTTPException(
                status_code=503, detail=f'UBI cannot be read: {error}'
            ) from error
        today = self._now().date()
        positions = []
        symbols = {}
        for row in snapshot.positions:
            entry = dataclasses.asdict(row)
            entry['day_pnl'] = snapshot.day_pnl_by_instrument.get(
                row.instrument_id
            )
            positions.append(entry)
            symbols[row.instrument_id] = row.symbol
        return {
            'total_balance': snapshot.total_balance,
            'margin_utilized': snapshot.margin_utilized,
            'day_pnl': snapshot.day_pnl,
            'week_pnl': self._shared.ledger.week_pnl(today),
            'trader_pnl': self._shared.risk_engine.trader_day_pnl(snapshot),
            'positions': positions,
            'holdings': snapshot.held_quantities,
            'owners': self._owners(symbols),
            'halts': self._shared.ledger.halts_in_force(today),
        }

    async def orders(
        self,
        kind: Literal['orders', 'trades', 'open_parents'] = 'orders',
    ) -> Any:
        """UBI's order book, as UBI serves it.

        Args:
            kind (Literal['orders', 'trades', 'open_parents']): Which book.

        Returns:
            Any: UBI's document.

        Raises:
            fastapi.HTTPException: UBI cannot be read (status 503).
        """
        reader = self._shared.reader
        try:
            return await reader.call(
                functools.partial(reader.get, _ORDER_BOOK_PATHS[kind])
            )
        except ubi_exceptions.UnifiedBrokerInterfaceError as error:
            raise fastapi.HTTPException(
                status_code=503, detail=f'UBI cannot be read: {error}'
            ) from error

    def trader_orders(self) -> dict[str, Any]:
        """Each trader's open orders in the trader order book, dry runs included.

        Returns:
            dict[str, Any]: The orders, keyed by trader name.
        """
        orders = {}
        for trader_name in self._trader_names:
            records = []
            for record in self._shared.order_book.open_orders(trader_name):
                records.append(dataclasses.asdict(record))
            orders[trader_name] = records
        return orders

    async def kill(self, request: KillRequest) -> dict[str, Any]:
        """Halts every trader until tomorrow and flattens the account.

        In dry_run mode the flatten is a dry run, exactly as when the loss limit fires it.

        Args:
            request (KillRequest): The confirmation and the reason.

        Returns:
            dict[str, Any]: UBI's answer to the flatten, or a note that the switch had already fired.

        Raises:
            fastapi.HTTPException: The confirmation is not FLATTEN (status 400).
        """
        if request.confirm != _CONFIRMATION:
            raise fastapi.HTTPException(
                status_code=400,
                detail='Send {"confirm": "FLATTEN"} to fire the kill switch.',
            )
        now = self._now()
        return await self._shared.kill_switch.trigger(
            f'The user fired the kill switch: {request.reason}',
            now.date() + datetime.timedelta(days=1),
            now,
        )

    def _owners(self, symbols: dict[str, str]) -> list[dict[str, str]]:
        """Every stock a trader owns now, with its symbol.

        The ledger knows only UBI's instrument ids, so the symbol comes from the open positions, or else from the trader's orders.

        Args:
            symbols (dict[str, str]): Symbols already known from the positions, keyed by instrument id.

        Returns:
            list[dict[str, str]]: Each owned instrument's id, symbol and trader; the symbol is the id when neither source knows it.
        """
        owners = []
        for instrument_id, trader_name in self._shared.ledger.owners().items():
            symbol = symbols.get(instrument_id)
            if symbol is None:
                for record in self._shared.order_book.open_orders(trader_name):
                    if record.instrument_id == instrument_id:
                        symbol = record.symbol
                        break
            owners.append(
                {
                    'instrument_id': instrument_id,
                    'symbol': symbol or instrument_id,
                    'trader': trader_name,
                }
            )
        return owners

    def _now(self) -> datetime.datetime:
        """The current time in India.

        Returns:
            datetime.datetime: The time.
        """
        if self._clock is not None:
            return self._clock()
        return datetime.datetime.now(_INDIA)
