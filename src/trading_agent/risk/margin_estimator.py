"""Estimates the margin an order blocks, with the rules UBI's own broker selector uses.

UBI has no route that returns an order's margin, but its documentation (architecture/broker-selection.md) states the rules its selector uses and how close they came to the brokers' calculators on 2026-09-30. The rates are deliberately high, because an estimate that is too high only refuses an order that could have gone through, while one that is too low lets through an order that is too large.

Typical usage example:

  margin = MarginEstimator(margin_configuration).margin(request)
"""

from trading_agent.configuration import agent_configuration
from trading_agent.risk import order_request as order_request_module


class MarginEstimator:
    """Estimates margin from quantity, price, product and segment."""

    def __init__(self, rates: agent_configuration.MarginRatesConfiguration):
        """Creates the estimator.

        Args:
            rates (agent_configuration.MarginRatesConfiguration): The margin rates per kind of instrument.
        """
        self._rates = rates

    def margin(self, request: order_request_module.OrderRequest) -> float:
        """Estimates the margin one order blocks.

        Args:
            request (order_request_module.OrderRequest): The order.

        Returns:
            float: The estimated margin in rupees.
        """
        value = request.quantity * request.price
        if request.is_option and request.transaction_type == 'buy':
            return value
        if request.is_option or request.is_future:
            return value * self.derivative_rate(request.segment)
        if request.product == 'mis':
            return value * self._rates.intraday_rate
        return value

    def derivative_rate(self, segment: str) -> float:
        """The margin rate for a future, or for a sold option, by kind of underlying.

        Args:
            segment (str): UBI's segment.

        Returns:
            float: The rate, such as 0.15 for index derivatives.
        """
        if 'commodity' in segment or segment.startswith('mcx'):
            return self._rates.commodity_derivative_rate
        if 'currency' in segment or segment.startswith('cds'):
            return self._rates.currency_derivative_rate
        if 'index' in segment:
            return self._rates.index_derivative_rate
        return self._rates.stock_derivative_rate
