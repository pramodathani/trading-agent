"""The cancel_order tool: cancels one of the trader's own orders, or one part of a bracket.

Cancelling takes risk away, so the risk engine is not asked; the trader order book only confirms that the trader placed the order. An order that has a parent_id is cancelled through UBI's order engine, which stops the whole order and every leg it has resting at a broker, so a bracket's exits go with it. A position the order already opened stays open.

Typical usage example:

  tool = CancelOrderTool(services, 'main', 'dry_run')
"""

import functools
from typing import Any

import pydantic
from tradingmachine.assets import instruments

from trading_agent.tools import order_tool
from trading_agent.tools import tool
from trading_agent.trading import trader_order_book as trader_order_book_module


class CancelOrderArguments(pydantic.BaseModel):
    """Which order to cancel.

    Attributes:
        parent_id: The parent_id that place_order or place_bracket_order answered with, or None.
        order_id: The broker's order_id, or None.
        part: With parent_id, the path of one part of a bracket to cancel alone, such as root.each_fill.children.1 for its target; or None for the whole order.
        reason: Why the trader is cancelling, kept in the journal.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    parent_id: str | None = None
    order_id: str | None = None
    part: str | None = None
    reason: str = pydantic.Field(min_length=1)

    @pydantic.model_validator(mode='after')
    def _require_one_order(self) -> CancelOrderArguments:
        """Checks that one order is named.

        Returns:
            CancelOrderArguments: These arguments, unchanged.

        Raises:
            ValueError: The order is not named exactly once, or part lacks a parent_id.
        """
        if (self.parent_id is None) == (self.order_id is None):
            raise ValueError('Give exactly one of parent_id and order_id')
        if self.part is not None and self.parent_id is None:
            raise ValueError('part needs the parent_id of its bracket')
        return self


class CancelOrderTool(order_tool.OrderTool):
    """Cancels one of the trader's own orders."""

    name = 'cancel_order'
    description = "Cancels one of this trader's own orders, named by the parent_id from place_order or place_bracket_order, or by the broker's order_id. Cancelling a bracket by its parent_id cancels its exits too; give part to cancel only one exit. A position the order already opened stays open: close it with place_order or flatten_trader. Give a short reason; it goes in the journal."
    arguments_model = CancelOrderArguments

    async def _act(self, arguments: CancelOrderArguments) -> tool.ToolResult:
        """Cancels the order.

        Args:
            arguments (CancelOrderArguments): The order.

        Returns:
            tool.ToolResult: UBI's answer, or why nothing was cancelled.
        """
        record = self._services.order_book.find(
            self._trader,
            arguments.parent_id,
            arguments.order_id,
        )
        if record is None:
            return tool.ToolResult.error(
                'This trader placed no order with that id, so it cannot cancel it. Use the parent_id or order_id from place_order or place_bracket_order, and see get_orders for the open orders.'
            )
        if record.state == trader_order_book_module.CANCELLED:
            return tool.ToolResult.error(
                f'Order {record.record_id} is already cancelled.'
            )
        note = self._mode_note()
        if record.dry_run:
            note = 'The order was a dry run that reached no broker, so the cancellation was only recorded.'
            answer = {
                'dry_run': True,
                'would_cancel': record.record_id,
                'part': arguments.part,
            }
        else:
            instrument = await self._instrument_by_id(record.instrument_id)
            answer = await self._services.reader.call(
                functools.partial(
                    self._send, instrument, record, arguments.part
                )
            )
        whole_order = arguments.part is None
        released = False
        if whole_order and (record.dry_run or not self._dry_run):
            self._services.order_book.mark_cancelled(record.record_id)
            released = await self._release_unused_claim(record.instrument_id)
        self._publish(
            {
                'action': 'cancelled',
                'kind': record.kind,
                'record_id': record.record_id,
                'part': arguments.part,
                'reason': arguments.reason,
                'released_claim': released,
            }
        )
        lines = [
            f'Cancelled order {record.record_id} ({record.transaction_type} {record.quantity} {record.symbol}). {note}',
        ]
        if released:
            lines.append(
                f'This trader has no other order and no position in {record.symbol}, so its claim on {record.symbol} was released and other traders may now trade it.'
            )
        lines.append('UBI answered:')
        lines.append(self._answer_text(answer))
        return tool.ToolResult.success('\n'.join(lines))

    def _send(
        self,
        instrument: instruments.TradeableInstrument,
        record: trader_order_book_module.OrderRecord,
        part: str | None,
    ) -> Any:
        """Sends the cancellation to UBI. It runs in a worker thread, under the UBI lock.

        Args:
            instrument (instruments.TradeableInstrument): The order's instrument.
            record (trader_order_book_module.OrderRecord): The order.
            part (str | None): One part of a bracket, or None for the whole order.

        Returns:
            Any: UBI's answer.
        """
        if record.parent_id is not None:
            return instrument.cancel_parent(
                record.parent_id,
                part=part,
                dry_run=self._dry_run,
            )
        return instrument.cancel_order(
            record.order_id,
            dry_run=self._dry_run,
        )
