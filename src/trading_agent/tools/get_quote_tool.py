"""The get_quote tool: the live quote of one instrument, with market depth.

Typical usage example:

  tool = GetQuoteTool(reader, formatter)
"""

import functools

from trading_agent.tools import broker_tool
from trading_agent.tools import tool
from trading_agent.trading import instrument_arguments


class GetQuoteTool(broker_tool.BrokerTool):
    """Reads one instrument's quote."""

    name = 'get_quote'
    description = 'Returns the live quote of one instrument: last price, open, high, low, close, volume, open interest and the best bids and offers. Name the instrument by instrument_id, or by exchange, segment and symbol (with underlying_symbol, expiry_date, strike_price and option_type for futures and options). Read-only.'
    arguments_model = instrument_arguments.InstrumentArguments

    async def run(
        self,
        arguments: instrument_arguments.InstrumentArguments,
    ) -> tool.ToolResult:
        """Reads the quote.

        Args:
            arguments (instrument_arguments.InstrumentArguments): The instrument.

        Returns:
            tool.ToolResult: The quote, or an error.
        """
        return await self._answer(functools.partial(self._read, arguments))

    def _read(
        self, arguments: instrument_arguments.InstrumentArguments
    ) -> dict:
        """Does the UBI work. It runs in a worker thread, under the UBI lock.

        Args:
            arguments (instrument_arguments.InstrumentArguments): The tool's arguments.

        Returns:
            dict: The instrument's quote.
        """
        return self._reader.instrument(arguments).quote
