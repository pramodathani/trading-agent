"""The place_order tool: one order in one instrument, checked by the risk engine first.

Typical usage example:

  tool = PlaceOrderTool(services, 'main', 'dry_run')
"""

import functools
from typing import Any

from tradingmachine.assets import instruments

from trading_agent.tools import order_tool
from trading_agent.tools import tool
from trading_agent.trading import order_arguments


class PlaceOrderTool(order_tool.OrderTool):
    """Places one plain order."""

    name = 'place_order'
    description = 'Places one order in one instrument. The risk engine checks it first and refuses it, with every reason, if it breaks a limit in TradingRules.md, the exchange is closed, or the instrument belongs to another desk or to the user. Name the instrument as for get_quote. quantity is in units, so for futures and options it is lots times lot size. A plain limit order is held inside UBI until the market reaches its price; a market order follows the book for up to 30 seconds. The answer gives a parent_id, the handle for modify_order and cancel_order. Give a short reason; it goes in the journal.'
    arguments_model = order_arguments.OrderArguments

    async def _act(
        self,
        arguments: order_arguments.OrderArguments,
    ) -> tool.ToolResult:
        """Checks the order with the risk engine and, when approved, sends it.

        Args:
            arguments (order_arguments.OrderArguments): The order.

        Returns:
            tool.ToolResult: UBI's answer with the order's handles, or why it was refused.
        """
        instrument = await self._instrument(arguments)
        lot_problem = self._lot_problem(instrument, arguments.quantity)
        if lot_problem is not None:
            return tool.ToolResult.error(lot_problem)
        price = await self._valuation_price(
            instrument,
            arguments.price,
            arguments.trigger_price,
        )
        if price is None:
            return tool.ToolResult.error(
                'UBI has no last price for this instrument, so a market order cannot be valued. Use a limit order with a price.'
            )
        request = self._order_request(
            instrument,
            arguments.transaction_type,
            arguments.quantity,
            arguments.product,
            price,
        )
        decision = await self._services.risk_engine.evaluate(request)
        if not decision.approved:
            return self._refusal(request, decision)
        answer = await self._services.reader.call(
            functools.partial(self._send, instrument, arguments)
        )
        record = self._remember('order', request, answer)
        self._publish(
            {
                'action': 'placed',
                'kind': 'order',
                'order': request.describe(),
                'order_type': arguments.order_type,
                'record_id': record.record_id,
                'parent_id': record.parent_id,
                'order_id': record.order_id,
                'reason': arguments.reason,
            }
        )
        return tool.ToolResult.success(
            '\n'.join(
                [
                    f'Placed: {request.describe()}, {arguments.order_type}. {self._mode_note()}',
                    f'parent_id: {record.parent_id}',
                    f'order_id: {record.order_id}',
                    f'Estimated margin: {decision.estimated_margin:,.2f}',
                    'UBI answered:',
                    self._answer_text(answer),
                ]
            )
        )

    def _send(
        self,
        instrument: instruments.TradeableInstrument,
        arguments: order_arguments.OrderArguments,
    ) -> Any:
        """Sends the order to UBI. It runs in a worker thread, under the UBI lock.

        Args:
            instrument (instruments.TradeableInstrument): The instrument.
            arguments (order_arguments.OrderArguments): The order.

        Returns:
            Any: UBI's answer.
        """
        return instrument.place_order(
            transaction_type=arguments.transaction_type,
            order_type=arguments.order_type,
            quantity=arguments.quantity,
            product=arguments.product,
            price=arguments.price,
            trigger_price=arguments.trigger_price,
            validity=arguments.validity,
            tag=self._tag,
            dry_run=self._dry_run,
        )
