"""What a trader wants to do, described for the risk engine.

Typical usage example:

  request = OrderRequest(trader='main', instrument_id='...', exchange='nse', segment='nse_equities', symbol='INFY', transaction_type='buy', quantity=10, product='cnc', price=1500.0)
"""

import dataclasses


@dataclasses.dataclass(frozen=True)
class OrderRequest:
    """One order before it is sent.

    Attributes:
        trader: The trader sending it.
        instrument_id: UBI's id for the instrument.
        exchange: The exchange, such as nse or mcx.
        segment: UBI's segment, such as nse_equities or nse_equity_index_options.
        symbol: The instrument's symbol, or its underlying's for a future or option.
        transaction_type: "buy" or "sell".
        quantity: How many units, which is lots times lot size for derivatives; always positive.
        product: "cnc", "mis" or "nrml".
        price: The price the order is valued at: its limit or trigger price, or the last price for a market order.
    """

    trader: str
    instrument_id: str
    exchange: str
    segment: str
    symbol: str
    transaction_type: str
    quantity: int
    product: str
    price: float

    @property
    def signed_quantity(self) -> int:
        """The change the order makes to the position: positive for a buy, negative for a sell."""
        if self.transaction_type == 'buy':
            return self.quantity
        return -self.quantity

    @property
    def is_option(self) -> bool:
        """Whether the instrument is an option."""
        return 'option' in self.segment

    @property
    def is_future(self) -> bool:
        """Whether the instrument is a future."""
        return 'future' in self.segment

    def describe(self) -> str:
        """A one-line description for messages and the journal.

        Returns:
            str: For example "buy 10 INFY (nse_equities, cnc) at 1500.0".
        """
        return f'{self.transaction_type} {self.quantity} {self.symbol} ({self.segment}, {self.product}) at {self.price:g}'
