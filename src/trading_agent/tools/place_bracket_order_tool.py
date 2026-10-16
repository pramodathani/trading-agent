"""The place_bracket_order tool: an entry order that sets up its own stop-loss and target when it fills.

UBI's order engine works the exits, so they act in real time even while the desk's model is busy or asleep: on the entry's first fill it places a stop-limit and a target sized to what filled, and when either exit fills it cancels the other. The risk engine checks the entry, because only the entry adds risk.

Typical usage example:

  tool = PlaceBracketOrderTool(services, 'main', 'dry_run')
"""

import functools
from typing import Any, Literal

import pydantic
from tradingmachine.assets import instruments
from tradingmachine.orders import bracket

from trading_agent.tools import order_tool
from trading_agent.tools import tool
from trading_agent.trading import order_arguments


class BracketOrderArguments(order_arguments.OrderArguments):
    """An entry order with its stop-loss and target.

    Attributes:
        order_type: The entry's type, "market" or "limit".
        stop_price: The stop-loss trigger in rupees, or None for no stop.
        stop_limit_price: The stop-loss's limit in rupees, needed with stop_price, because every stop is a stop-limit; for a long position it is at or below stop_price.
        target_price: The target's limit in rupees, or None for no target.
    """

    order_type: Literal['market', 'limit']
    stop_price: float | None = pydantic.Field(default=None, gt=0)
    stop_limit_price: float | None = pydantic.Field(default=None, gt=0)
    target_price: float | None = pydantic.Field(default=None, gt=0)

    @pydantic.model_validator(mode='after')
    def _require_an_exit(self) -> BracketOrderArguments:
        """Checks that there is a stop, a target or both, and that a stop has its limit.

        Returns:
            BracketOrderArguments: These arguments, unchanged.

        Raises:
            ValueError: There is no exit, or a stop has no limit.
        """
        if self.stop_price is None and self.target_price is None:
            raise ValueError('Give a stop_price, a target_price or both')
        if self.stop_price is not None and self.stop_limit_price is None:
            raise ValueError(
                'A stop needs a stop_limit_price, because every stop is a stop-limit'
            )
        if self.stop_price is None and self.stop_limit_price is not None:
            raise ValueError('stop_limit_price needs a stop_price')
        return self


class PlaceBracketOrderTool(order_tool.OrderTool):
    """Places one bracket order."""

    name = 'place_bracket_order'
    description = 'Places an entry order that, on its first fill, sets up a stop-loss (a stop-limit: stop_price triggers it, stop_limit_price is its limit) and a target, worked by UBI in real time. When one exit fills, the other is cancelled. For a buy, the stop is below the entry and the target above; for a sell, the other way round. The risk engine checks the entry first, as for place_order. Use it to enter with protection, especially for intraday and scalping. The answer gives a parent_id for modify_order (with part to change one exit) and cancel_order. Give a short reason; it goes in the journal.'
    arguments_model = BracketOrderArguments

    async def _act(self, arguments: BracketOrderArguments) -> tool.ToolResult:
        """Checks the entry with the risk engine and, when approved, sends the bracket.

        Args:
            arguments (BracketOrderArguments): The bracket.

        Returns:
            tool.ToolResult: UBI's answer with the order's handles, or why it was refused.
        """
        instrument = await self._instrument(arguments)
        lot_problem = self._lot_problem(instrument, arguments.quantity)
        if lot_problem is not None:
            return tool.ToolResult.error(lot_problem)
        price = await self._valuation_price(instrument, arguments.price, None)
        if price is None:
            return tool.ToolResult.error(
                'UBI has no last price for this instrument, so a market entry cannot be valued. Use a limit entry with a price.'
            )
        side_problem = self._side_problem(arguments, price)
        if side_problem is not None:
            return tool.ToolResult.error(side_problem)
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
        record = self._remember('bracket', request, answer)
        self._publish(
            {
                'action': 'placed',
                'kind': 'bracket',
                'order': request.describe(),
                'order_type': arguments.order_type,
                'stop_price': arguments.stop_price,
                'stop_limit_price': arguments.stop_limit_price,
                'target_price': arguments.target_price,
                'record_id': record.record_id,
                'parent_id': record.parent_id,
                'reason': arguments.reason,
            }
        )
        return tool.ToolResult.success(
            '\n'.join(
                [
                    f'Placed a bracket: {request.describe()}, {arguments.order_type}, stop {arguments.stop_price} (limit {arguments.stop_limit_price}), target {arguments.target_price}. {self._mode_note()}',
                    f'parent_id: {record.parent_id}',
                    f'Estimated margin: {decision.estimated_margin:,.2f}',
                    'UBI answered:',
                    self._answer_text(answer),
                ]
            )
        )

    def _side_problem(
        self,
        arguments: BracketOrderArguments,
        entry_price: float,
    ) -> str | None:
        """Checks that the stop and the target are on the right sides of the entry.

        Args:
            arguments (BracketOrderArguments): The bracket.
            entry_price (float): The entry's limit price, or the last price for a market entry.

        Returns:
            str | None: The problem, or None when the exits are placed sensibly.
        """
        stop = arguments.stop_price
        stop_limit = arguments.stop_limit_price
        target = arguments.target_price
        if arguments.transaction_type == 'buy':
            if stop is not None and stop >= entry_price:
                return f'For a buy, the stop_price {stop:g} must be below the entry price {entry_price:g}.'
            if stop is not None and stop_limit > stop:
                return f'For a buy, the stop is a sell, so its stop_limit_price {stop_limit:g} must be at or below the stop_price {stop:g}.'
            if target is not None and target <= entry_price:
                return f'For a buy, the target_price {target:g} must be above the entry price {entry_price:g}.'
            return None
        if stop is not None and stop <= entry_price:
            return f'For a sell, the stop_price {stop:g} must be above the entry price {entry_price:g}.'
        if stop is not None and stop_limit < stop:
            return f'For a sell, the stop is a buy, so its stop_limit_price {stop_limit:g} must be at or above the stop_price {stop:g}.'
        if target is not None and target >= entry_price:
            return f'For a sell, the target_price {target:g} must be below the entry price {entry_price:g}.'
        return None

    def _send(
        self,
        instrument: instruments.TradeableInstrument,
        arguments: BracketOrderArguments,
    ) -> Any:
        """Sends the bracket to UBI. It runs in a worker thread, under the UBI lock.

        Args:
            instrument (instruments.TradeableInstrument): The instrument.
            arguments (BracketOrderArguments): The bracket.

        Returns:
            Any: UBI's answer.
        """
        order = bracket.BracketOrder(
            instrument,
            transaction_type=arguments.transaction_type,
            product=arguments.product,
            order_type=arguments.order_type,
            quantity=arguments.quantity,
            price=arguments.price,
            validity=arguments.validity,
            tag=self._tag,
            dry_run=self._dry_run,
            stop_price=arguments.stop_price,
            stop_limit_price=arguments.stop_limit_price,
            target_price=arguments.target_price,
        )
        return order.place()
