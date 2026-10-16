"""The arguments a model gives to place an order: the instrument, the order itself and the reason for it.

The price fields are checked against the order type here, as UBI would check them, so a model learns of a missing price at once and in plain words.

Typical usage example:

  arguments = OrderArguments(exchange='nse', segment='equities', symbol='INFY', transaction_type='buy', quantity=10, product='mis', order_type='limit', price=1500.0, reason='Breakout above the previous high')
"""

from typing import Literal

import pydantic

from trading_agent.trading import instrument_arguments

_NEEDS_PRICE = {
    'limit',
    'sl',
}
_NEEDS_TRIGGER = {
    'sl',
    'sl-m',
}


class OrderArguments(instrument_arguments.InstrumentArguments):
    """One order in one instrument.

    Attributes:
        transaction_type: "buy" or "sell".
        quantity: How many units, which is lots times lot size for futures and options.
        product: "cnc" for delivery, "mis" for intraday, "nrml" for carried futures and options.
        order_type: "market", "limit", "sl" (stop-limit) or "sl-m" (stop-market).
        price: The limit price in rupees, needed for limit and sl orders and not allowed otherwise.
        trigger_price: The trigger price in rupees, needed for sl and sl-m orders and not allowed otherwise.
        validity: "day" or "ioc", or None for day.
        reason: Why the desk is placing the order, kept in the journal.
    """

    transaction_type: Literal['buy', 'sell']
    quantity: int = pydantic.Field(gt=0)
    product: Literal['cnc', 'mis', 'nrml']
    order_type: Literal['market', 'limit', 'sl', 'sl-m']
    price: float | None = pydantic.Field(default=None, gt=0)
    trigger_price: float | None = pydantic.Field(default=None, gt=0)
    validity: Literal['day', 'ioc'] | None = None
    reason: str = pydantic.Field(min_length=1)

    @pydantic.model_validator(mode='after')
    def _match_prices_to_order_type(self) -> OrderArguments:
        """Checks that the price and trigger price suit the order type.

        Returns:
            OrderArguments: These arguments, unchanged.

        Raises:
            ValueError: A price or trigger price is missing or not allowed for the order type.
        """
        if self.order_type in _NEEDS_PRICE and self.price is None:
            raise ValueError(f'A {self.order_type} order needs a price')
        if self.order_type not in _NEEDS_PRICE and self.price is not None:
            raise ValueError(
                f'A {self.order_type} order takes no price; leave price out'
            )
        if self.order_type in _NEEDS_TRIGGER and self.trigger_price is None:
            raise ValueError(f'A {self.order_type} order needs a trigger_price')
        if (
            self.order_type not in _NEEDS_TRIGGER
            and self.trigger_price is not None
        ):
            raise ValueError(
                f'A {self.order_type} order takes no trigger_price; leave it out'
            )
        return self
