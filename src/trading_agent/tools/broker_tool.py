"""The shallow base class of the read-only trading tools.

Typical usage example:

  class GetQuoteTool(BrokerTool):
      ...
"""

from collections.abc import Callable
from typing import Any

from tradingmachine.assets import exceptions as instrument_exceptions
from tradingmachine.unified_broker_interface import exceptions as ubi_exceptions

from trading_agent.tools import tool
from trading_agent.trading import broker_reader as broker_reader_module
from trading_agent.trading import result_formatter as result_formatter_module

_BROKER_TIMEOUT_SECONDS = 60.0


class BrokerTool(tool.Tool):
    """A tool that reads from UBI through tradingmachine."""

    timeout_seconds = _BROKER_TIMEOUT_SECONDS

    def __init__(
        self,
        reader: broker_reader_module.BrokerReader,
        formatter: result_formatter_module.ResultFormatter,
    ):
        """Creates the tool.

        Args:
            reader (broker_reader_module.BrokerReader): The shared reader of UBI.
            formatter (result_formatter_module.ResultFormatter): Turns tradingmachine's answers into text.
        """
        self._reader = reader
        self._formatter = formatter

    async def _answer(
        self,
        work: Callable[[], Any],
        rows: int = 50,
    ) -> tool.ToolResult:
        """Runs the UBI work and formats its answer, or explains why it failed.

        Args:
            work (Callable[[], Any]): The work, run in a worker thread.
            rows (int): For a table, how many of the last rows to keep.

        Returns:
            tool.ToolResult: The formatted answer, or an error the model can act on.
        """
        try:
            value = await self._reader.call(work)
        except instrument_exceptions.InstrumentError as error:
            return tool.ToolResult.error(
                f'Instrument problem: {error}. Check the fields, or find the instrument with search_instruments.'
            )
        except ubi_exceptions.UnifiedBrokerInterfaceError as error:
            return tool.ToolResult.error(
                f'UBI refused or failed the request: {type(error).__name__}: {error}'
            )
        return tool.ToolResult.success(self._formatter.format(value, rows=rows))
