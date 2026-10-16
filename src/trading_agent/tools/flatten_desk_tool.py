"""The flatten_desk tool: cancels every open order of the desk and closes every position the desk owns.

It touches only what the desk itself placed or owns, never another desk's trades or the user's own holdings; flattening the whole account is left to the kill switch and to the user. Each closing order passes the risk engine, which always lets a desk reduce its own position but still checks that the exchange is open.

Typical usage example:

  tool = FlattenDeskTool(services, 'main', 'dry_run')
"""

import functools
from typing import Any

import pydantic
from tradingmachine.assets import exceptions as instrument_exceptions
from tradingmachine.assets import instruments
from tradingmachine.unified_broker_interface import exceptions as ubi_exceptions

from trading_agent.tools import order_tool
from trading_agent.tools import tool
from trading_agent.trading import desk_order_book as desk_order_book_module

_ORDER_PRODUCTS = {
    'intraday': 'mis',
    'delivery': 'cnc',
    'carry': 'nrml',
}


class FlattenDeskArguments(pydantic.BaseModel):
    """Why the desk is flattening.

    Attributes:
        reason: Why, kept in the journal.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    reason: str = pydantic.Field(min_length=1)


class FlattenDeskTool(order_tool.OrderTool):
    """Cancels the desk's orders and closes the desk's positions."""

    name = 'flatten_desk'
    description = "Cancels every open order this desk placed and closes every position and holding this desk owns with market orders, leaving other desks and the user's own holdings alone. Use it to get flat fast, such as before the intraday square-off or when a trade has gone wrong. Each step is reported; a step that fails is listed so it can be retried. Give a short reason; it goes in the journal."
    arguments_model = FlattenDeskArguments

    async def _act(self, arguments: FlattenDeskArguments) -> tool.ToolResult:
        """Cancels, then closes, and reports every step.

        Args:
            arguments (FlattenDeskArguments): The reason.

        Returns:
            tool.ToolResult: One line per order cancelled and per position closed.
        """
        lines = [
            self._heading(),
        ]
        lines.extend(await self._cancel_open_orders())
        lines.extend(await self._close_positions())
        if len(lines) == 1:
            lines.append('The desk had no open orders and no positions.')
        self._publish(
            {
                'action': 'flattened',
                'kind': 'flatten_desk',
                'steps': lines[1:],
                'reason': arguments.reason,
            }
        )
        return tool.ToolResult.success('\n'.join(lines))

    def _heading(self) -> str:
        """The first line of the report, saying whether anything is real.

        Returns:
            str: The line.
        """
        if self._dry_run:
            return f'Flattening the {self._desk} desk as a dry run: nothing is sent to a broker.'
        return f'Flattening the {self._desk} desk, live.'

    async def _cancel_open_orders(self) -> list[str]:
        """Cancels each of the desk's open orders, one at a time.

        Returns:
            list[str]: One line per order.
        """
        lines = []
        order_book = self._services.order_book
        for record in order_book.open_orders(self._desk):
            if record.dry_run:
                order_book.mark_cancelled(record.record_id)
                lines.append(
                    f'Cancelled dry-run order {record.record_id} ({record.transaction_type} {record.quantity} {record.symbol}); it had reached no broker.'
                )
                continue
            try:
                instrument = await self._instrument_by_id(record.instrument_id)
                await self._services.reader.call(
                    functools.partial(self._cancel, instrument, record)
                )
            except (
                ubi_exceptions.ConflictError,
                ubi_exceptions.NotFoundError,
            ):
                if not self._dry_run:
                    order_book.mark_cancelled(record.record_id)
                lines.append(
                    f'Order {record.record_id} ({record.symbol}) had already finished.'
                )
                continue
            except ubi_exceptions.UnifiedBrokerInterfaceError as error:
                lines.append(
                    f'Could not cancel order {record.record_id} ({record.symbol}): {type(error).__name__}: {error}'
                )
                continue
            if not self._dry_run:
                order_book.mark_cancelled(record.record_id)
            lines.append(
                f'Cancelled order {record.record_id} ({record.transaction_type} {record.quantity} {record.symbol}).'
            )
        return lines

    async def _close_positions(self) -> list[str]:
        """Closes each position and holding the desk owns, one at a time.

        Returns:
            list[str]: One line per instrument.
        """
        try:
            snapshot = await self._services.snapshot_reader.read()
        except ubi_exceptions.UnifiedBrokerInterfaceError as error:
            return [
                f'Could not read the positions from UBI, so nothing was closed: {type(error).__name__}: {error}',
            ]
        owned = self._services.ledger.owned_by(self._desk)
        lines = []
        closed = set()
        for row in snapshot.positions:
            if row.instrument_id not in owned or row.quantity == 0:
                continue
            closed.add(row.instrument_id)
            product = _ORDER_PRODUCTS.get(row.product, 'nrml')
            lines.append(
                await self._close(
                    row.instrument_id,
                    row.quantity,
                    product,
                    row.product,
                )
            )
        for instrument_id, quantity in snapshot.held_quantities.items():
            if instrument_id not in owned or instrument_id in closed:
                continue
            if quantity <= 0:
                continue
            lines.append(
                await self._close(instrument_id, quantity, 'cnc', None)
            )
        return lines

    async def _close(
        self,
        instrument_id: str,
        signed_quantity: int,
        product: str,
        position_product: str | None,
    ) -> str:
        """Closes one position or holding with a market order, after the risk engine agrees.

        Args:
            instrument_id (str): The instrument.
            signed_quantity (int): The position: positive when long, negative when short.
            product (str): The order product, "cnc", "mis" or "nrml".
            position_product (str | None): UBI's position product, such as intraday, to close the whole position by; None to sell a holding by its quantity.

        Returns:
            str: One line saying what happened.
        """
        try:
            instrument = await self._instrument_by_id(instrument_id)
            transaction_type = 'sell'
            if signed_quantity < 0:
                transaction_type = 'buy'
            price = await self._valuation_price(instrument, None, None)
            if price is None:
                price = 0.0
            request = self._order_request(
                instrument,
                transaction_type,
                abs(signed_quantity),
                product,
                price,
            )
            decision = await self._services.risk_engine.evaluate(request)
            if not decision.approved:
                return f'Could not close {request.symbol}: ' + ' '.join(
                    decision.reasons
                )
            answer = await self._services.reader.call(
                functools.partial(
                    self._send_close,
                    instrument,
                    transaction_type,
                    abs(signed_quantity),
                    product,
                    position_product,
                )
            )
        except (
            ubi_exceptions.UnifiedBrokerInterfaceError,
            instrument_exceptions.InstrumentError,
        ) as error:
            return f'Could not close {instrument_id}: {type(error).__name__}: {error}'
        record = self._remember('close', request, answer)
        outcome = None
        if isinstance(answer, dict):
            outcome = answer.get('outcome')
        return f'Closed {request.describe()} with a market order (parent_id {record.parent_id}, outcome {outcome}).'

    def _cancel(
        self,
        instrument: instruments.TradeableInstrument,
        record: desk_order_book_module.OrderRecord,
    ) -> Any:
        """Cancels one order at UBI. It runs in a worker thread, under the UBI lock.

        Args:
            instrument (instruments.TradeableInstrument): The order's instrument.
            record (desk_order_book_module.OrderRecord): The order.

        Returns:
            Any: UBI's answer.
        """
        if record.parent_id is not None:
            return instrument.cancel_parent(
                record.parent_id, dry_run=self._dry_run
            )
        return instrument.cancel_order(record.order_id, dry_run=self._dry_run)

    def _send_close(
        self,
        instrument: instruments.TradeableInstrument,
        transaction_type: str,
        quantity: int,
        product: str,
        position_product: str | None,
    ) -> Any:
        """Sends one closing market order to UBI. It runs in a worker thread, under the UBI lock.

        Args:
            instrument (instruments.TradeableInstrument): The instrument.
            transaction_type (str): "buy" or "sell".
            quantity (int): How many units.
            product (str): "cnc", "mis" or "nrml".
            position_product (str | None): UBI's position product to close the whole position by, or None to sell by quantity.

        Returns:
            Any: UBI's answer.
        """
        if position_product is None:
            return instrument.place_order(
                transaction_type=transaction_type,
                order_type='market',
                quantity=quantity,
                product=product,
                tag=self._tag,
                dry_run=self._dry_run,
            )
        return instrument.place_order(
            transaction_type=transaction_type,
            order_type='market',
            quantity=None,
            product=product,
            tag=self._tag,
            dry_run=self._dry_run,
            quantity_reference={
                'kind': 'liquidate_position',
                'product': position_product,
            },
        )
