"""Tests for the read-only trading tools, the result formatter and the instrument arguments, with a fake UBI."""

import asyncio
import math

import numpy
import pandas
import pydantic
import pytest
from tradingmachine.assets import exceptions as instrument_exceptions
from tradingmachine.unified_broker_interface import exceptions as ubi_exceptions

from trading_agent.tools import get_portfolio_tool
from trading_agent.tools import get_quote_tool
from trading_agent.trading import instrument_arguments
from trading_agent.trading import result_formatter


class _FakeInstrument:
    """Stands in for a tradingmachine Instrument.

    Attributes:
        quote: The quote it reports.
    """

    def __init__(self, quote: dict):
        """Creates the instrument.

        Args:
            quote (dict): The quote it reports.
        """
        self.quote = quote


class _FakeReader:
    """Stands in for BrokerReader: runs work directly and answers from fixed data.

    Attributes:
        paths: The UBI routes requested.
    """

    def __init__(self, answer: object = None, failure: Exception | None = None):
        """Creates the reader.

        Args:
            answer (object): What every request returns.
            failure (Exception | None): An exception every request raises instead, or None.
        """
        self._answer = answer
        self._failure = failure
        self.paths = []

    async def call(self, work):
        """Runs the work at once.

        Args:
            work (Callable): The work.

        Returns:
            object: What the work returned.
        """
        return work()

    def get(self, path: str, parameters: dict | None = None) -> object:
        """Answers a route.

        Args:
            path (str): The route.
            parameters (dict | None): Its parameters, unused.

        Returns:
            object: The fixed answer.

        Raises:
            Exception: The configured failure.
        """
        del parameters
        self.paths.append(path)
        if self._failure is not None:
            raise self._failure
        return self._answer

    def instrument(
        self, arguments: instrument_arguments.InstrumentArguments
    ) -> _FakeInstrument:
        """Builds a fake instrument.

        Args:
            arguments (instrument_arguments.InstrumentArguments): The instrument's name.

        Returns:
            _FakeInstrument: The instrument.

        Raises:
            Exception: The configured failure.
        """
        del arguments
        if self._failure is not None:
            raise self._failure
        return _FakeInstrument(self._answer)


def _nifty() -> instrument_arguments.InstrumentArguments:
    """Names the Nifty index.

    Returns:
        instrument_arguments.InstrumentArguments: The arguments.
    """
    return instrument_arguments.InstrumentArguments(
        exchange='nse',
        segment='equity_indices',
        symbol='NIFTY',
    )


class TestResultFormatter:
    """Tests for turning tradingmachine values into text."""

    def test_table_keeps_the_last_rows_as_csv(self) -> None:
        """A table is cut to its last rows, with a line saying how many there were."""
        frame = pandas.DataFrame(
            {
                'close': [
                    1.0,
                    2.0,
                    3.0,
                ],
            }
        )

        text = result_formatter.ResultFormatter().format(frame, rows=2)

        assert (
            text
            == '3 rows; the last 2 are shown, oldest first.\nclose\n2.0\n3.0'
        )

    def test_numpy_values_dates_and_missing_numbers_become_plain_json(
        self,
    ) -> None:
        """NumPy numbers become plain numbers, timestamps become text, and NaN becomes null."""
        value = {
            'last_price': numpy.float64(23146.15),
            'average_price': math.nan,
            'time': pandas.Timestamp('2026-10-16 15:30', tz='Asia/Kolkata'),
        }

        text = result_formatter.ResultFormatter().format(value)

        assert '"last_price": 23146.15' in text
        assert '"average_price": null' in text
        assert '"time": "2026-10-16T15:30:00+05:30"' in text

    def test_none_means_no_data(self) -> None:
        """None from tradingmachine, such as no candles for a range, reads as "No data."."""
        assert result_formatter.ResultFormatter().format(None) == 'No data.'


class TestInstrumentArguments:
    """Tests for naming an instrument."""

    def test_id_or_exchange_and_segment_is_required(self) -> None:
        """Arguments with neither an id nor an exchange and segment are refused."""
        with pytest.raises(pydantic.ValidationError, match='instrument_id'):
            instrument_arguments.InstrumentArguments(symbol='INFY')

    def test_option_type_must_be_ce_or_pe(self) -> None:
        """An option type other than CE or PE is refused."""
        with pytest.raises(pydantic.ValidationError):
            instrument_arguments.InstrumentArguments(
                exchange='nse',
                segment='equity_options',
                underlying_symbol='NIFTY',
                expiry_date='2026-10-27',
                strike_price=23000,
                option_type='CALL',
            )


class TestBrokerTools:
    """Tests for the tools' answers and error messages."""

    def test_quote_is_formatted(self) -> None:
        """get_quote returns the instrument's quote as JSON."""
        reader = _FakeReader(
            answer={
                'last_price': 23146.15,
            }
        )
        tool = get_quote_tool.GetQuoteTool(
            reader, result_formatter.ResultFormatter()
        )

        result = asyncio.run(tool.run(_nifty()))

        assert not result.is_error
        assert '"last_price": 23146.15' in result.text

    def test_unknown_instrument_suggests_searching(self) -> None:
        """An InstrumentError becomes an error that points to search_instruments."""
        reader = _FakeReader(
            failure=instrument_exceptions.InstrumentError(
                'no instrument NOSUCH'
            )
        )
        tool = get_quote_tool.GetQuoteTool(
            reader, result_formatter.ResultFormatter()
        )

        result = asyncio.run(tool.run(_nifty()))

        assert result.is_error
        assert 'search_instruments' in result.text

    def test_ubi_failure_names_the_error(self) -> None:
        """A UBI error becomes an error result naming its type, instead of an exception."""
        reader = _FakeReader(
            failure=ubi_exceptions.ServiceUnavailableError(
                'broker down', 503, None
            )
        )
        tool = get_portfolio_tool.GetPortfolioTool(
            reader, result_formatter.ResultFormatter()
        )

        result = asyncio.run(
            tool.run(get_portfolio_tool.GetPortfolioArguments(kind='funds'))
        )

        assert result.is_error
        assert 'ServiceUnavailableError' in result.text
        assert reader.paths == [
            '/api/portfolio/funds',
        ]
