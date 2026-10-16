"""How a model names one instrument, as tool arguments.

The fields follow tradingmachine_mcp's InstrumentDescription, which follows tradingmachine's own Instrument constructor: either UBI's id, or the exchange and segment with the identity fields the segment needs.

Typical usage example:

  arguments = InstrumentArguments(exchange='nse', segment='equities', symbol='INFY')
"""

import pydantic


class InstrumentArguments(pydantic.BaseModel):
    """One instrument.

    Attributes:
        instrument_id: UBI's id for the instrument; when given, the other fields are ignored.
        exchange: The lower-case exchange, such as nse, bse or mcx.
        segment: The segment, such as equities, equity_indices, equity_futures or equity_options.
        symbol: The symbol of a share, index or fund, such as INFY or NIFTY; empty for futures and options.
        underlying_symbol: What a future or option is written on, such as NIFTY.
        expiry_date: A future's or option's expiry, as YYYY-MM-DD.
        strike_price: An option's strike price.
        option_type: CE for a call or PE for a put.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    instrument_id: str | None = None
    exchange: str | None = None
    segment: str | None = None
    symbol: str | None = None
    underlying_symbol: str | None = None
    expiry_date: str | None = pydantic.Field(
        default=None,
        pattern=r'^\d{4}-\d{2}-\d{2}$',
    )
    strike_price: float | None = pydantic.Field(default=None, gt=0)
    option_type: str | None = pydantic.Field(
        default=None,
        pattern=r'^(CE|PE)$',
    )

    @pydantic.model_validator(mode='after')
    def _require_a_name(self) -> InstrumentArguments:
        """Checks that the instrument is named by an id or by exchange and segment.

        Returns:
            InstrumentArguments: These arguments, unchanged.

        Raises:
            ValueError: Neither an instrument_id nor both exchange and segment were given.
        """
        if self.instrument_id is None and (
            self.exchange is None or self.segment is None
        ):
            raise ValueError(
                'Give either instrument_id, or exchange and segment with the identity fields'
            )
        return self
