"""The get_candles tool: price candles of one instrument over a range.

Typical usage example:

  tool = GetCandlesTool(reader, formatter)
"""

import functools

import pandas
import pydantic

from trading_agent.tools import broker_tool
from trading_agent.tools import tool
from trading_agent.trading import instrument_arguments

_DEFAULT_DAYS = 30


class GetCandlesArguments(instrument_arguments.InstrumentArguments):
    """The arguments of get_candles: the instrument's fields plus the range.

    Attributes:
        interval: The candle length, such as day, 60minute, 15minute, 5minute or minute.
        days: How many days to count back from today; used when from_date is not given.
        from_date: The first day, as YYYY-MM-DD.
        to_date: The last day, as YYYY-MM-DD; needed with from_date.
        rows: How many of the most recent candles to return.
    """

    interval: str = 'day'
    days: int | None = pydantic.Field(default=None, ge=1, le=3650)
    from_date: str | None = pydantic.Field(
        default=None, pattern=r'^\d{4}-\d{2}-\d{2}$'
    )
    to_date: str | None = pydantic.Field(
        default=None, pattern=r'^\d{4}-\d{2}-\d{2}$'
    )
    rows: int = pydantic.Field(default=50, ge=1, le=500)


class GetCandlesTool(broker_tool.BrokerTool):
    """Reads one instrument's candles."""

    name = 'get_candles'
    description = 'Returns price candles (datetime in India time, open, high, low, close, volume, oi) for one instrument, oldest first, keeping the most recent rows. Give days, or from_date and to_date; with neither, the last 30 days. The candle of the latest day may not be stored until after the close, so use get_quote for the current prices. Name the instrument as for get_quote. Read-only.'
    arguments_model = GetCandlesArguments

    async def run(self, arguments: GetCandlesArguments) -> tool.ToolResult:
        """Reads the candles.

        Args:
            arguments (GetCandlesArguments): The instrument and range.

        Returns:
            tool.ToolResult: The candles as CSV, or an error.
        """
        return await self._answer(
            functools.partial(self._read, arguments),
            rows=arguments.rows,
        )

    def _read(self, arguments: GetCandlesArguments) -> pandas.DataFrame | None:
        """Reads the candles. It runs in a worker thread, under the UBI lock.

        Args:
            arguments (GetCandlesArguments): The instrument and range.

        Returns:
            pandas.DataFrame | None: The candles, or None when UBI has none for the range.
        """
        days = arguments.days
        if days is None and arguments.from_date is None:
            days = _DEFAULT_DAYS
        return self._reader.instrument(arguments).prices(
            interval=arguments.interval,
            from_date=arguments.from_date,
            to_date=arguments.to_date,
            days=days,
        )
