"""Reads the NIFTY index's market state that Jev is shown: the live quote and the latest 5-minute candles.

The state is built by code from UBI, not written by a model, so Jev always judges the same kind of facts.

Typical usage example:

  reader_of_state = NiftyMarketState(broker_reader, candle_count=24)
  state = await reader_of_state.read()
"""

import datetime
import json
import zoneinfo
from collections.abc import Callable
from typing import Any

from trading_agent.trading import broker_reader as broker_reader_module
from trading_agent.trading import instrument_arguments

_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')
_QUOTE_FIELDS = (
    'last_price',
    'ohlc',
    'previous_close',
    'change_percent',
)
_CANDLE_COLUMNS = (
    'datetime',
    'open',
    'high',
    'low',
    'close',
    'volume',
)
NIFTY_INDEX = instrument_arguments.InstrumentArguments(
    exchange='nse',
    segment='equity_indices',
    symbol='NIFTY',
)


class NiftyMarketState:
    """Reads NIFTY's quote and candles from UBI and turns them into a JSON-safe state."""

    def __init__(
        self,
        reader: broker_reader_module.BrokerReader,
        candle_count: int,
        clock: Callable[[], datetime.datetime] | None = None,
    ):
        """Creates the state reader.

        Args:
            reader (broker_reader_module.BrokerReader): The shared UBI reader.
            candle_count (int): How many of the latest 5-minute candles to include.
            clock (Callable[[], datetime.datetime] | None): Returns the current time; None uses the system clock.
        """
        self._reader = reader
        self._candle_count = candle_count
        self._clock = clock

    async def read(self) -> dict[str, Any]:
        """Reads the state now.

        Returns:
            dict[str, Any]: The time in India, the quote's headline fields and the latest candles, oldest first.

        Raises:
            UnifiedBrokerInterfaceError: UBI could not give the quote or the candles.
            InstrumentError: UBI does not know the NIFTY index.
        """
        quote, candles = await self._reader.call(self._read_from_ubi)
        now = self._now()
        return {
            'instrument': 'NIFTY 50 index, NSE',
            'time_in_india': now.strftime('%Y-%m-%d %H:%M:%S'),
            'quote': quote,
            'candle_interval': '5 minutes',
            'candles_oldest_first': candles,
        }

    def _read_from_ubi(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Does the UBI work. It runs in a worker thread, under the UBI lock.

        Returns:
            tuple[dict[str, Any], list[dict[str, Any]]]: A tuple (quote, candles), where quote holds the quote's headline fields and candles holds one dict per candle.
        """
        instrument = self._reader.instrument(NIFTY_INDEX)
        full_quote = instrument.quote
        quote = {}
        for field in _QUOTE_FIELDS:
            if field in full_quote:
                quote[field] = full_quote[field]
        frame = instrument.prices(
            interval='5minute',
            from_date=None,
            to_date=None,
            days=3,
        )
        candles = []
        if frame is not None and len(frame.index) > 0:
            columns = []
            for column in _CANDLE_COLUMNS:
                if column in frame.columns:
                    columns.append(column)
            latest = frame[columns].tail(self._candle_count).copy()
            if 'datetime' in latest.columns:
                latest['datetime'] = latest['datetime'].astype(str)
            candles = json.loads(latest.to_json(orient='records'))
        return self._json_safe(quote), candles

    def _json_safe(self, value: dict[str, Any]) -> dict[str, Any]:
        """Turns values such as datetimes into strings, so the state can be sent as JSON.

        Args:
            value (dict[str, Any]): The values.

        Returns:
            dict[str, Any]: The same values, JSON-safe.
        """
        return json.loads(json.dumps(value, default=str))

    def _now(self) -> datetime.datetime:
        """The current time in India.

        Returns:
            datetime.datetime: Now.
        """
        if self._clock is not None:
            return self._clock().astimezone(_INDIA)
        return datetime.datetime.now(_INDIA)
