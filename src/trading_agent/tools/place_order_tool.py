"""The place_order tool: one order in one instrument, checked by the risk engine first.

Typical usage example:

  tool = PlaceOrderTool(services, 'main', 'dry_run')
"""

import functools
from typing import Any

import pydantic
from tradingmachine.assets import instruments

from trading_agent.tools import order_tool
from trading_agent.tools import tool
from trading_agent.trading import order_arguments


class PlaceOrderArguments(order_arguments.OrderArguments):
    """One plain order, which may be an after-market order.

    Attributes:
        after_market: True to queue the order at the broker while the exchange is closed, so it goes to the exchange when the exchange next opens.
    """

    after_market: bool = False

    @pydantic.model_validator(mode='after')
    def _keep_after_market_orders_for_the_day(self) -> PlaceOrderArguments:
        """Checks that an after-market order is a day order.

        Returns:
            PlaceOrderArguments: These arguments, unchanged.

        Raises:
            ValueError: An after-market order asks for ioc validity.
        """
        if self.after_market and self.validity == 'ioc':
            raise ValueError(
                'An after-market order waits for the open, so it cannot be ioc; leave validity out'
            )
        return self


class PlaceOrderTool(order_tool.OrderTool):
    """Places one plain order."""

    name = 'place_order'
    description = 'Places one order in one instrument. The risk engine checks it first and refuses it, with every reason, if it breaks a limit in TradingRules.md, the exchange is closed, or the instrument belongs to another trader or to the user. Name the instrument as for get_quote. quantity is in units, so for futures and options it is lots times lot size. A plain limit order is held inside UBI until the market reaches its price; a market order follows the book for up to 30 seconds. While the exchange is closed, set after_market to true to queue the order at the broker for the next open, preferably as a limit order; the broker sends it to the exchange when the exchange opens, and an after-market order is refused while the exchange is open. The answer gives a parent_id, the handle for modify_order and cancel_order. Give a short reason; it goes in the journal.'
    arguments_model = PlaceOrderArguments

    async def _act(
        self,
        arguments: PlaceOrderArguments,
    ) -> tool.ToolResult:
        """Checks the order with the risk engine and, when approved, sends it.

        Args:
            arguments (PlaceOrderArguments): The order.

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
            arguments.after_market,
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
        arguments: PlaceOrderArguments,
    ) -> Any:
        """Sends the order to UBI. It runs in a worker thread, under the UBI lock.

        Args:
            instrument (instruments.TradeableInstrument): The instrument.
            arguments (PlaceOrderArguments): The order.

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
            after_market=arguments.after_market,
            tag=self._tag,
            dry_run=self._dry_run,
        )
