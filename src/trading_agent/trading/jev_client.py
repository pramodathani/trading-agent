"""Asks TypeSafe AI's Jev decision model whether NIFTY looks like a buy, a sell or a hold.

Jev writes no text: it answers a question by choosing one of the answers it is given, with a probability for each. This client asks one choice question about a market state and returns the decision.

Typical usage example:

  client = JevClient(jev_configuration, api_key)
  decision = await client.decide({'index': 'NIFTY', 'last_price': 24350.15})
"""

import dataclasses
from typing import Any

import httpx

from trading_agent.configuration import agent_configuration

_QUESTION_ID = 'direction'
_INSTRUCTIONS = 'Judging only from this NIFTY index market state, which way is NIFTY most likely to move over the next 5 to 15 minutes?'
CRITERIA = {
    'buy': 'NIFTY is likely to rise enough over the next 5 to 15 minutes to pay for a short long trade.',
    'sell': 'NIFTY is likely to fall enough over the next 5 to 15 minutes to pay for a short bearish trade.',
    'hold': 'There is no clear short-term move, or the signals conflict, so no trade should be opened.',
}


class JevError(Exception):
    """Jev could not be asked, or its answer could not be read."""


@dataclasses.dataclass(frozen=True)
class JevDecision:
    """One answer from Jev.

    Attributes:
        choice: The chosen answer: buy, sell or hold.
        confidence: How peaked Jev's probabilities are, from 0 to 1.
        probabilities: The probability of each answer, keyed by answer.
        model: The exact Jev version that answered, such as jev-1.14.0.
    """

    choice: str
    confidence: float
    probabilities: dict[str, float]
    model: str


class JevClient:
    """Sends choice questions to Jev over TypeSafe's HTTP API."""

    def __init__(
        self,
        configuration: agent_configuration.JevConfiguration,
        api_key: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        """Creates the client.

        Args:
            configuration (agent_configuration.JevConfiguration): The API's address, the model and the timeout.
            api_key (str): The TypeSafe API key.
            transport (httpx.AsyncBaseTransport | None): The HTTP transport, replaced in tests; None uses the network.
        """
        self._configuration = configuration
        self._api_key = api_key
        self._transport = transport

    async def decide(self, state: dict[str, Any]) -> JevDecision:
        """Asks Jev for the direction of NIFTY in a market state.

        Args:
            state (dict[str, Any]): The market state, as JSON-safe values.

        Returns:
            JevDecision: Jev's answer.

        Raises:
            JevError: The request failed, or the answer was not a buy, sell or hold.
        """
        body = {
            'model': self._configuration.model,
            'state': state,
            'questions': {
                _QUESTION_ID: {
                    'type': 'choice',
                    'instructions': _INSTRUCTIONS,
                    'criteria': CRITERIA,
                },
            },
        }
        headers = {
            'Authorization': f'Bearer {self._api_key}',
            'Content-Type': 'application/json',
        }
        url = self._configuration.base_url.rstrip('/') + '/systemone'
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=self._configuration.timeout_seconds,
            ) as client:
                response = await client.post(url, json=body, headers=headers)
        except httpx.HTTPError as error:
            raise JevError(
                f'Jev could not be reached: {type(error).__name__}: {error}'
            ) from error
        if response.status_code != 200:
            raise JevError(
                f'Jev refused the request with HTTP {response.status_code}: {response.text[:300]}'
            )
        try:
            payload = response.json()
        except ValueError as error:
            raise JevError(
                'Jev answered with something other than JSON'
            ) from error
        return self._decision(payload)

    def _decision(self, payload: Any) -> JevDecision:
        """Reads the decision out of Jev's answer.

        Args:
            payload (Any): The decoded JSON answer.

        Returns:
            JevDecision: The decision.

        Raises:
            JevError: The answer lacks the direction question's choice, or chose something unknown.
        """
        if not isinstance(payload, dict):
            raise JevError(
                f'Jev answered with an unexpected shape: {payload!r}'
            )
        answers = payload.get('answers')
        if not isinstance(answers, dict):
            raise JevError(f'Jev answered without answers: {payload!r}')
        answer = answers.get(_QUESTION_ID)
        if not isinstance(answer, dict):
            raise JevError(
                f'Jev did not answer the direction question: {payload!r}'
            )
        choice = answer.get('choice')
        if choice not in CRITERIA:
            raise JevError(f'Jev chose an unknown answer: {choice=}')
        probabilities = {}
        raw_probabilities = answer.get('probabilities') or {}
        for name in CRITERIA:
            probabilities[name] = float(raw_probabilities.get(name, 0.0))
        return JevDecision(
            choice=choice,
            confidence=float(answer.get('confidence', 0.0)),
            probabilities=probabilities,
            model=str(payload.get('model', self._configuration.model)),
        )
