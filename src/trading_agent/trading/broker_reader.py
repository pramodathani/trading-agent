"""The one place trading-agent reads from UBI, through tradingmachine.

tradingmachine is synchronous, so every call runs in a worker thread and the desks keep working while UBI answers. A lock lets one UBI call run at a time, as the tradingmachine_mcp server does, because UBI holds a single access token and broker rate limits are shared.

The client is built from tradingmachine's own `.env`, named in trading_agent.toml. Left to itself, tradingmachine would look for a `.env` in the working folder and find trading-agent's, which has no UBI settings.

Typical usage example:

  reader = BrokerReader(Path('/home/pramod/Projects/tradingmachine/.env'))
  quote = await reader.call(lambda: reader.instrument(arguments).quote)
"""

import asyncio
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from tradingmachine.assets import instruments
from tradingmachine.unified_broker_interface import client as ubi_client
from tradingmachine.utilities import (
    configuration as tradingmachine_configuration,
)

from trading_agent.trading import (
    instrument_arguments as instrument_arguments_module,
)

_Result = TypeVar('_Result')


class BrokerReader:
    """Reads instruments, prices, the portfolio and the order book from UBI."""

    def __init__(self, environment_file: Path):
        """Remembers where tradingmachine's settings are, without connecting.

        Args:
            environment_file (Path): tradingmachine's `.env` file.
        """
        self._environment_file = environment_file
        self._client = None
        self._lock = threading.Lock()

    async def call(self, work: Callable[[], _Result]) -> _Result:
        """Runs one piece of UBI work in a worker thread, one at a time.

        Args:
            work (Callable[[], _Result]): The work, such as reading a quote.

        Returns:
            _Result: What the work returned.

        Raises:
            tradingmachine.unified_broker_interface.exceptions.UnifiedBrokerInterfaceError: UBI refused or failed the request.
            tradingmachine.assets.exceptions.InstrumentError: The instrument does not exist.
        """
        return await asyncio.to_thread(self._locked, work)

    def get(self, path: str, parameters: dict[str, Any] | None = None) -> Any:
        """Sends a GET request to one of UBI's read routes. Call it inside call().

        Args:
            path (str): The route, such as /api/portfolio/funds.
            parameters (dict[str, Any] | None): The query parameters, or None.

        Returns:
            Any: UBI's decoded JSON answer.
        """
        return self._shared_client().get(path, params=parameters)

    def instrument(
        self,
        arguments: instrument_arguments_module.InstrumentArguments,
    ) -> instruments.Instrument:
        """Looks an instrument up as a plain Instrument, which has no order methods. Call it inside call().

        Args:
            arguments (instrument_arguments_module.InstrumentArguments): How the model named the instrument.

        Returns:
            instruments.Instrument: The instrument.
        """
        shared_client = self._shared_client()
        if arguments.instrument_id is not None:
            return instruments.Instrument(
                instrument_id=arguments.instrument_id,
                unified_broker_interface=shared_client,
            )
        return instruments.Instrument(
            exchange=arguments.exchange,
            segment=arguments.segment,
            symbol=arguments.symbol,
            underlying_symbol=arguments.underlying_symbol,
            expiry_date=arguments.expiry_date,
            strike_price=arguments.strike_price,
            option_type=arguments.option_type,
            unified_broker_interface=shared_client,
        )

    def _locked(self, work: Callable[[], _Result]) -> _Result:
        """Runs the work while holding the UBI lock.

        Args:
            work (Callable[[], _Result]): The work.

        Returns:
            _Result: What the work returned.
        """
        with self._lock:
            return work()

    def _shared_client(self) -> ubi_client.UnifiedBrokerInterface:
        """The UBI client, built on first use from tradingmachine's settings.

        Returns:
            ubi_client.UnifiedBrokerInterface: The client.
        """
        if self._client is None:
            settings = tradingmachine_configuration.Configuration(
                environment_file=str(self._environment_file),
            )
            self._client = ubi_client.UnifiedBrokerInterface(
                project_configuration=settings,
            )
        return self._client
