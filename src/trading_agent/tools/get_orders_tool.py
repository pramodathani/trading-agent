"""The get_orders tool: the order book, the trades, or the orders UBI's engine is holding.

Typical usage example:

  tool = GetOrdersTool(reader, formatter)
"""

import functools
from typing import Any, Literal

import pydantic

from trading_agent.tools import broker_tool
from trading_agent.tools import tool

_ORDER_BOOK_PATHS = {
    'orders': '/api/orders/details',
    'trades': '/api/orders/trades',
    'open_parents': '/api/orders/parents',
}


class GetOrdersArguments(pydantic.BaseModel):
    """The arguments of get_orders.

    Attributes:
        kind: "orders" for today's orders at the brokers, "trades" for today's fills, "open_parents" for orders UBI's engine is still holding or working, such as limit orders and stops.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    kind: Literal['orders', 'trades', 'open_parents']


class GetOrdersTool(broker_tool.BrokerTool):
    """Reads the order book."""

    name = 'get_orders'
    description = "Returns today's orders, today's trades (fills), or the open parents: orders UBI's own engine is still holding or working, which is where plain limit orders and stops wait. Every desk shares this account. Read-only."
    arguments_model = GetOrdersArguments

    async def run(self, arguments: GetOrdersArguments) -> tool.ToolResult:
        """Reads the order book.

        Args:
            arguments (GetOrdersArguments): Which book.

        Returns:
            tool.ToolResult: UBI's answer, or an error.
        """
        return await self._answer(functools.partial(self._read, arguments))

    def _read(self, arguments: GetOrdersArguments) -> Any:
        """Does the UBI work. It runs in a worker thread, under the UBI lock.

        Args:
            arguments (GetOrdersArguments): The tool's arguments.

        Returns:
            Any: UBI's answer.
        """
        return self._reader.get(_ORDER_BOOK_PATHS[arguments.kind])
