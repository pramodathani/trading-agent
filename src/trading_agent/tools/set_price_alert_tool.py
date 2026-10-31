"""The set_price_alert tool: asks the market watcher to wake the trader when a price is reached.

Typical usage example:

  tool = SetPriceAlertTool(reader, store)
"""

import functools
from typing import Literal

import pydantic
from tradingmachine.assets import exceptions as instrument_exceptions
from tradingmachine.assets import instruments
from tradingmachine.unified_broker_interface import exceptions as ubi_exceptions

from trading_agent.scheduling import (
    price_alert_store as price_alert_store_module,
)
from trading_agent.tools import tool
from trading_agent.trading import broker_reader as broker_reader_module
from trading_agent.trading import instrument_arguments


class SetPriceAlertArguments(instrument_arguments.InstrumentArguments):
    """The arguments of set_price_alert.

    Attributes:
        condition: "above" to fire when the price rises to or past it, "below" when it falls to or past it.
        price: The price, in rupees.
        note: What you want to do when it fires, so your future self knows.
    """

    condition: Literal['above', 'below']
    price: float = pydantic.Field(gt=0)
    note: str = ''


class SetPriceAlertTool(tool.Tool):
    """Adds a price alert."""

    name = 'set_price_alert'
    description = 'Asks the market watcher to wake you once when an instrument trades at or above, or at or below, a price, while the market is open. Name the instrument as for get_quote. Add a note saying what you plan to do then. The alert is removed when it fires. It is refused when the price is already on that side, because it would fire at once.'
    arguments_model = SetPriceAlertArguments

    def __init__(
        self,
        reader: broker_reader_module.BrokerReader,
        store: price_alert_store_module.PriceAlertStore,
    ):
        """Creates the tool.

        Args:
            reader (broker_reader_module.BrokerReader): The shared UBI reader.
            store (price_alert_store_module.PriceAlertStore): The trader's alerts.
        """
        self._reader = reader
        self._store = store

    async def run(self, arguments: SetPriceAlertArguments) -> tool.ToolResult:
        """Checks the instrument and the current price, then stores the alert.

        Args:
            arguments (SetPriceAlertArguments): The instrument, side, price and note.

        Returns:
            tool.ToolResult: The alert and every active alert, or why it was refused.
        """
        try:
            instrument = await self._reader.call(
                functools.partial(self._reader.tradeable_instrument, arguments)
            )
            last_price = await self._reader.call(
                functools.partial(self._last_price, instrument)
            )
        except (
            ubi_exceptions.UnifiedBrokerInterfaceError,
            instrument_exceptions.InstrumentError,
        ) as error:
            return tool.ToolResult.error(f'{type(error).__name__}: {error}')
        alert = price_alert_store_module.PriceAlert.new(
            instrument_id=instrument.instrument_id,
            exchange=instrument.exchange,
            segment=instrument.segment,
            symbol=instrument.symbol or instrument.underlying_symbol or '',
            condition=arguments.condition,
            price=arguments.price,
            note=arguments.note,
        )
        if last_price is not None and alert.is_crossed(last_price):
            return tool.ToolResult.error(
                f'{alert.symbol} is already at {last_price:,.2f}, {arguments.condition} {arguments.price:,.2f}, so the alert would fire at once.'
            )
        self._store.add(alert)
        lines = [
            f'Alert {alert.alert_id} set: {alert.describe()}. The last price is {last_price}.',
            'Your active alerts:',
        ]
        for active in self._store.alerts():
            lines.append(f'- {active.alert_id}: {active.describe()}')
        return tool.ToolResult.success('\n'.join(lines))

    def _last_price(
        self,
        instrument: instruments.TradeableInstrument,
    ) -> float | None:
        """Reads an instrument's last traded price. It runs in a worker thread, under the UBI lock.

        Args:
            instrument (instruments.TradeableInstrument): The instrument.

        Returns:
            float | None: The price, or None when UBI has none.
        """
        return instrument.last_price
