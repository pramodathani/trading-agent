"""The search_instruments tool: finds securities whose trading symbol contains some text.

Typical usage example:

  tool = SearchInstrumentsTool(reader, formatter)
"""

import functools

import pydantic

from trading_agent.tools import broker_tool
from trading_agent.tools import tool

_SEARCH_PATH = '/api/instruments/search'


class SearchInstrumentsArguments(pydantic.BaseModel):
    """The arguments of search_instruments.

    Attributes:
        exchange: The lower-case exchange, such as nse, bse or mcx.
        segment: The segment, such as equities or equity_indices.
        text: Text the trading symbol must contain, such as INFY or RELI; company names do not match.
        limit: The most results to return.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    exchange: str = pydantic.Field(min_length=2)
    segment: str = pydantic.Field(min_length=2)
    text: str = pydantic.Field(min_length=1)
    limit: int = pydantic.Field(default=20, ge=1, le=200)


class SearchInstrumentsTool(broker_tool.BrokerTool):
    """Searches UBI's instrument list by trading symbol."""

    name = 'search_instruments'
    description = 'Finds securities in one exchange and segment whose trading symbol contains some text, with their instrument_id. UBI matches trading symbols only, so search INFY or RELI, not Infosys or Reliance. Read-only.'
    arguments_model = SearchInstrumentsArguments

    async def run(
        self, arguments: SearchInstrumentsArguments
    ) -> tool.ToolResult:
        """Runs the search.

        Args:
            arguments (SearchInstrumentsArguments): Where and what to search.

        Returns:
            tool.ToolResult: The matching instruments, best match first, or an error.
        """
        return await self._answer(functools.partial(self._read, arguments))

    def _read(self, arguments: SearchInstrumentsArguments) -> list:
        """Does the UBI work. It runs in a worker thread, under the UBI lock.

        Args:
            arguments (SearchInstrumentsArguments): The tool's arguments.

        Returns:
            list: The matching instruments, best match first.
        """
        answer = self._reader.get(
            _SEARCH_PATH,
            {
                'exchange': arguments.exchange,
                'segment': arguments.segment,
                'q': arguments.text,
                'limit': arguments.limit,
            },
        )
        return answer['instruments']
