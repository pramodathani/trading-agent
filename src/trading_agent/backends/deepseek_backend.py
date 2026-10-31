"""A backend for DeepSeek's API, which speaks OpenAI's Chat Completions protocol with three differences that matter here.

1. Thinking mode, on by default, returns the model's thinking as reasoning_content. When tools are offered, DeepSeek requires that thinking to be sent back with every earlier assistant message, in every later request, or it refuses with a 400 error; the conversation keeps it for that reason.
2. Prompt tokens are priced by whether DeepSeek's cache held them, and off-peak hours cost less. The usage report gives prompt_cache_hit_tokens and prompt_cache_miss_tokens, so each call's cost is worked out from the prices in trading_agent.toml.
3. A 402 Insufficient Balance error means the account's credit is used up. The router then leaves DeepSeek alone for 15 minutes before trying again, so a top-up is noticed without a request on every turn.

Typical usage example:

  backend = DeepSeekBackend('deepseek', backend_configuration, api_key)
  reply = await backend.complete(conversation, registry.definitions(), on_text)
"""

import datetime
from collections.abc import Callable
from typing import Any

import openai

from trading_agent.agent import messages
from trading_agent.backends import backend
from trading_agent.backends import openai_compatible_backend
from trading_agent.configuration import agent_configuration

_NO_CREDIT_STATUS = 402
_NO_CREDIT_RETRY_SECONDS = 900.0
_TOKENS_PER_PRICE_UNIT = 1_000_000
_LAST_WEEKDAY = 4


class DeepSeekBackend(openai_compatible_backend.OpenAICompatibleBackend):
    """One DeepSeek model, with its thinking sent back and its cost worked out per call."""

    def __init__(
        self,
        name: str,
        backend_configuration: agent_configuration.BackendConfiguration,
        api_key: str,
        clock: Callable[[], datetime.datetime] | None = None,
    ):
        """Creates the backend without contacting DeepSeek.

        Args:
            name (str): The backend's name in trading_agent.toml.
            backend_configuration (agent_configuration.BackendConfiguration): Its settings, of kind "deepseek".
            api_key (str): The DeepSeek API key.
            clock (Callable[[], datetime.datetime] | None): The source of the current UTC time, replaceable in tests; None uses the real clock.
        """
        super().__init__(name, backend_configuration, api_key)
        self._configuration = backend_configuration
        self._clock = clock or self._utc_now

    def _assistant_extras(
        self, message: messages.ConversationMessage
    ) -> dict[str, Any]:
        """Sends the model's earlier thinking back with its message, as DeepSeek requires when tools are offered.

        Args:
            message (messages.ConversationMessage): The assistant message.

        Returns:
            dict[str, Any]: {"reasoning_content": ...} when the message has thinking, else nothing.
        """
        if not message.reasoning:
            return {}
        return {
            'reasoning_content': message.reasoning,
        }

    def _unavailable(
        self, error: openai.APIError
    ) -> backend.BackendUnavailableError:
        """Turns a failed request into a router error, waiting 15 minutes when the credit is used up.

        Args:
            error (openai.APIError): The failure.

        Returns:
            backend.BackendUnavailableError: The error to raise.
        """
        status = getattr(error, 'status_code', None)
        if status == _NO_CREDIT_STATUS:
            return backend.BackendUnavailableError(
                f'DeepSeek backend {self.name} has no credit left (402 Insufficient Balance); trying again in 15 minutes.',
                _NO_CREDIT_RETRY_SECONDS,
            )
        return backend.BackendUnavailableError(
            f'DeepSeek backend {self.name} failed: {error!r}'
        )

    def _cache_read_tokens(self, usage: Any) -> int:
        """How many prompt tokens DeepSeek's cache held.

        Args:
            usage (Any): The completion's usage object.

        Returns:
            int: The prompt_cache_hit_tokens DeepSeek reported, or 0.
        """
        return int(getattr(usage, 'prompt_cache_hit_tokens', 0) or 0)

    def _cost_usd(self, usage: Any, cache_read_tokens: int) -> float | None:
        """Works out the call's cost from the configured peak prices and the time of day.

        Args:
            usage (Any): The completion's usage object.
            cache_read_tokens (int): The prompt tokens the cache held.

        Returns:
            float | None: The cost in US dollars, or None when a price is not configured or the user switched to a model whose prices are not configured.
        """
        configuration = self._configuration
        if self.model != self.configured_model:
            return None
        hit_price = configuration.usd_per_million_cache_hit_tokens
        miss_price = configuration.usd_per_million_cache_miss_tokens
        completion_price = configuration.usd_per_million_completion_tokens
        if hit_price is None or miss_price is None or completion_price is None:
            return None
        missed = int(getattr(usage, 'prompt_cache_miss_tokens', 0) or 0)
        if missed == 0:
            missed = max(usage.prompt_tokens - cache_read_tokens, 0)
        peak_cost = (
            cache_read_tokens * hit_price
            + missed * miss_price
            + usage.completion_tokens * completion_price
        ) / _TOKENS_PER_PRICE_UNIT
        if self.is_peak(self._clock()):
            return peak_cost
        return peak_cost * configuration.off_peak_price_factor

    def is_peak(self, moment: datetime.datetime) -> bool:
        """Says whether a moment falls in DeepSeek's peak hours: the configured UTC periods, Monday to Friday.

        Chinese public holidays, which DeepSeek prices as off-peak, are not known here, so those days are counted at the peak price.

        Args:
            moment (datetime.datetime): The moment, with a time zone.

        Returns:
            bool: True in a peak period on a weekday.
        """
        utc = moment.astimezone(datetime.UTC)
        if utc.weekday() > _LAST_WEEKDAY:
            return False
        minute = utc.hour * 60 + utc.minute
        for period in self._configuration.peak_hours_utc:
            start_text, _, end_text = period.partition('-')
            start = self._minutes(start_text)
            end = self._minutes(end_text)
            if start <= minute < end:
                return True
        return False

    @staticmethod
    def _minutes(clock_text: str) -> int:
        """Turns "HH:MM" into minutes after midnight.

        Args:
            clock_text (str): Such as "06:00".

        Returns:
            int: The minutes.
        """
        hours, _, minutes = clock_text.strip().partition(':')
        return int(hours) * 60 + int(minutes or 0)

    @staticmethod
    def _utc_now() -> datetime.datetime:
        """The current time in UTC.

        Returns:
            datetime.datetime: Now.
        """
        return datetime.datetime.now(datetime.UTC)
