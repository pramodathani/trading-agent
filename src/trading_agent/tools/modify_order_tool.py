"""The modify_order tool: changes the quantity, price or trigger price of one of the trader's own open orders.

A trader can change only an order it placed, as the trader order book records. Making an order bigger adds risk, so the extra quantity goes through the risk engine as if it were a new order; a smaller order or a new price does not. A dry-run order reached no broker, so changing it is only recorded.

Typical usage example:

  tool = ModifyOrderTool(services, 'main', 'dry_run')
"""

import functools
from typing import Any

import pydantic
from tradingmachine.assets import instruments

from trading_agent.risk import order_request as order_request_module
from trading_agent.tools import order_tool
from trading_agent.tools import tool
from trading_agent.trading import trader_order_book as trader_order_book_module


class ModifyOrderArguments(pydantic.BaseModel):
    """Which order to change, and how.

    Attributes:
        parent_id: The parent_id that place_order or place_bracket_order answered with, for an order UBI is still holding or for one part of a bracket; or None.
        order_id: The broker's order_id, for an order already at a broker; or None.
        part: With parent_id, the path of one part of a bracket that has not been sent yet, such as root.each_fill.children.0 for its stop, as get_orders open_parents lists it; or None.
        quantity: The new total quantity in units, counting what has filled, or None to keep it.
        price: The new limit price in rupees, or None to keep it.
        trigger_price: The new trigger price in rupees, or None to keep it.
        reason: Why the trader is changing the order, kept in the journal.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    parent_id: str | None = None
    order_id: str | None = None
    part: str | None = None
    quantity: int | None = pydantic.Field(default=None, gt=0)
    price: float | None = pydantic.Field(default=None, gt=0)
    trigger_price: float | None = pydantic.Field(default=None, gt=0)
    reason: str = pydantic.Field(min_length=1)

    @pydantic.model_validator(mode='after')
    def _require_an_order_and_a_change(self) -> ModifyOrderArguments:
        """Checks that one order is named and that something changes.

        Returns:
            ModifyOrderArguments: These arguments, unchanged.

        Raises:
            ValueError: The order is not named once, part lacks a parent_id, or nothing changes.
        """
        if (self.parent_id is None) == (self.order_id is None):
            raise ValueError('Give exactly one of parent_id and order_id')
        if self.part is not None and self.parent_id is None:
            raise ValueError('part needs the parent_id of its bracket')
        if (
            self.quantity is None
            and self.price is None
            and self.trigger_price is None
        ):
            raise ValueError('Give a new quantity, price or trigger_price')
        return self


class ModifyOrderTool(order_tool.OrderTool):
    """Changes one of the trader's own orders."""

    name = 'modify_order'
    description = "Changes the quantity, price or trigger price of one of this trader's own open orders. Name it by the parent_id from place_order or place_bracket_order (an order UBI is still holding), or by the broker's order_id (an order already at a broker). To move one exit of a bracket before it is sent, give the bracket's parent_id and the part, as get_orders open_parents lists it. A bigger quantity is checked by the risk engine like a new order. Give a short reason; it goes in the journal."
    arguments_model = ModifyOrderArguments

    async def _act(self, arguments: ModifyOrderArguments) -> tool.ToolResult:
        """Checks the change and sends it.

        Args:
            arguments (ModifyOrderArguments): The change.

        Returns:
            tool.ToolResult: UBI's answer, or why the change was not made.
        """
        record = self._services.order_book.find(
            self._trader,
            arguments.parent_id,
            arguments.order_id,
        )
        if record is None:
            return tool.ToolResult.error(
                'This trader placed no order with that id, so it cannot change it. Use the parent_id or order_id from place_order or place_bracket_order, and see get_orders for the open orders.'
            )
        if record.state == trader_order_book_module.CANCELLED:
            return tool.ToolResult.error(
                f'Order {record.record_id} was cancelled, so it cannot be changed.'
            )
        new_quantity = record.quantity
        if arguments.quantity is not None and arguments.part is None:
            new_quantity = arguments.quantity
        new_price = record.price
        if arguments.price is not None and arguments.part is None:
            new_price = arguments.price
        if new_quantity > record.quantity:
            extra = order_request_module.OrderRequest(
                trader=self._trader,
                instrument_id=record.instrument_id,
                exchange=record.exchange,
                segment=record.segment,
                symbol=record.symbol,
                transaction_type=record.transaction_type,
                quantity=new_quantity - record.quantity,
                product=record.product,
                price=new_price,
            )
            decision = await self._services.risk_engine.evaluate(extra)
            if not decision.approved:
                return self._refusal(extra, decision)
        note = self._mode_note()
        if record.dry_run:
            note = 'The order was a dry run that reached no broker, so the change was only recorded.'
            answer = {
                'dry_run': True,
                'would_modify': record.record_id,
                'part': arguments.part,
                'quantity': arguments.quantity,
                'price': arguments.price,
                'trigger_price': arguments.trigger_price,
            }
        else:
            instrument = await self._instrument_by_id(record.instrument_id)
            answer = await self._services.reader.call(
                functools.partial(self._send, instrument, arguments)
            )
        if record.dry_run or not self._dry_run:
            self._services.order_book.change(
                record.record_id, new_quantity, new_price
            )
        self._publish(
            {
                'action': 'modified',
                'kind': record.kind,
                'record_id': record.record_id,
                'part': arguments.part,
                'quantity': arguments.quantity,
                'price': arguments.price,
                'trigger_price': arguments.trigger_price,
                'reason': arguments.reason,
            }
        )
        return tool.ToolResult.success(
            '\n'.join(
                [
                    f'Changed order {record.record_id} ({record.transaction_type} {record.symbol}). {note}',
                    'UBI answered:',
                    self._answer_text(answer),
                ]
            )
        )

    def _send(
        self,
        instrument: instruments.TradeableInstrument,
        arguments: ModifyOrderArguments,
    ) -> Any:
        """Sends the change to UBI. It runs in a worker thread, under the UBI lock.

        Args:
            instrument (instruments.TradeableInstrument): The order's instrument.
            arguments (ModifyOrderArguments): The change.

        Returns:
            Any: UBI's answer.
        """
        return instrument.modify_order(
            order_id=arguments.order_id,
            quantity=arguments.quantity,
            price=arguments.price,
            trigger_price=arguments.trigger_price,
            dry_run=self._dry_run,
            parent_id=arguments.parent_id,
            part=arguments.part,
        )
