"""Reads NIFTY's market state and asks Jev for its direction, for the jev_decision tool and the Jev signal watcher.

Typical usage example:

  adviser = JevAdviser(market_state, client)
  advice = await adviser.advise()
  print(advice.decision.choice)
"""

import dataclasses
from typing import Any

from tradingmachine.assets import exceptions as instrument_exceptions
from tradingmachine.unified_broker_interface import exceptions as ubi_exceptions

from trading_agent.trading import jev_client as jev_client_module
from trading_agent.trading import (
    nifty_market_state as nifty_market_state_module,
)


@dataclasses.dataclass(frozen=True)
class JevAdvice:
    """Jev's decision together with the state it judged.

    Attributes:
        decision: Jev's answer.
        state: The NIFTY market state Jev was shown.
    """

    decision: jev_client_module.JevDecision
    state: dict[str, Any]

    def describe(self) -> str:
        """Describes the advice in a few sentences for a trader to read.

        Returns:
            str: The choice, the confidence, every probability and what Jev was shown.
        """
        decision = self.decision
        probability_parts = []
        for name, probability in decision.probabilities.items():
            probability_parts.append(f'{name} {probability:.2f}')
        quote = self.state.get('quote') or {}
        last_price = quote.get('last_price')
        price_text = 'an unknown price'
        if isinstance(last_price, (int, float)):
            price_text = f'{last_price:,.2f}'
        candle_count = len(self.state.get('candles_oldest_first') or [])
        probabilities_text = ', '.join(probability_parts)
        return (
            f'Jev ({decision.model}) says {decision.choice.upper()} with confidence {decision.confidence:.2f}. '
            f'Probabilities: {probabilities_text}. '
            f'It judged NIFTY at {price_text} at {self.state.get("time_in_india")} India time, with the latest {candle_count} five-minute candles.'
        )


class JevAdviserError(Exception):
    """The market state could not be read, or Jev could not answer."""


class JevAdviser:
    """Asks Jev about NIFTY's direction now."""

    def __init__(
        self,
        market_state: nifty_market_state_module.NiftyMarketState,
        client: jev_client_module.JevClient,
    ):
        """Creates the adviser.

        Args:
            market_state (nifty_market_state_module.NiftyMarketState): Reads NIFTY's state from UBI.
            client (jev_client_module.JevClient): Asks Jev.
        """
        self._market_state = market_state
        self._client = client

    async def advise(self) -> JevAdvice:
        """Reads the state and asks Jev.

        Returns:
            JevAdvice: The decision and the state it was based on.

        Raises:
            JevAdviserError: UBI could not give NIFTY's state, or Jev failed.
        """
        try:
            state = await self._market_state.read()
        except (
            ubi_exceptions.UnifiedBrokerInterfaceError,
            instrument_exceptions.InstrumentError,
        ) as error:
            raise JevAdviserError(
                f"NIFTY's market state could not be read from UBI: {type(error).__name__}: {error}"
            ) from error
        if not state.get('quote'):
            raise JevAdviserError(
                'UBI gave no NIFTY quote, so Jev was not asked.'
            )
        try:
            decision = await self._client.decide(state)
        except jev_client_module.JevError as error:
            raise JevAdviserError(str(error)) from error
        return JevAdvice(decision=decision, state=state)
