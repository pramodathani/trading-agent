"""The get_portfolio tool: the account's positions, holdings or funds across every broker.

Typical usage example:

  tool = GetPortfolioTool(reader, formatter)
"""

import functools
from typing import Any, Literal

import pydantic

from trading_agent.tools import broker_tool
from trading_agent.tools import tool

_PORTFOLIO_PATHS = {
    'positions': '/api/portfolio/positions',
    'holdings': '/api/portfolio/holdings',
    'funds': '/api/portfolio/funds',
}


class GetPortfolioArguments(pydantic.BaseModel):
    """The arguments of get_portfolio.

    Attributes:
        kind: "positions" for today's and carried positions, "holdings" for delivery holdings, "funds" for balances and margins.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    kind: Literal['positions', 'holdings', 'funds']


class GetPortfolioTool(broker_tool.BrokerTool):
    """Reads one part of the portfolio."""

    name = 'get_portfolio'
    description = "Returns the account's positions, holdings or funds across every connected broker, as UBI reports them. The account is shared by every desk. Read-only."
    arguments_model = GetPortfolioArguments

    async def run(self, arguments: GetPortfolioArguments) -> tool.ToolResult:
        """Reads the part of the portfolio.

        Args:
            arguments (GetPortfolioArguments): Which part.

        Returns:
            tool.ToolResult: UBI's answer, or an error.
        """
        return await self._answer(functools.partial(self._read, arguments))

    def _read(self, arguments: GetPortfolioArguments) -> Any:
        """Does the UBI work. It runs in a worker thread, under the UBI lock.

        Args:
            arguments (GetPortfolioArguments): The tool's arguments.

        Returns:
            Any: UBI's answer.
        """
        return self._reader.get(_PORTFOLIO_PATHS[arguments.kind])
