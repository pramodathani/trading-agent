"""Counts each desk's model usage today, and keeps Claude's latest subscription limit status, for /usage.

It listens to the model_usage and rate_limit events every backend publishes. Totals are per India day, desk and backend: model calls, prompt tokens, completion tokens and, for Claude, tokens read from the prompt cache and what the same usage would cost on the API. An OpenAI-compatible backend whose prices are set in trading_agent.toml also gets its cost in rupees. When the gateway starts, today's journal is read back, so a restart does not reset the day's totals.

Typical usage example:

  tracker = UsageTracker(event_bus, layout, ['main'], backends)
  task = asyncio.create_task(tracker.run())
  text = tracker.summary_text('main')
"""

import dataclasses
import datetime
import json
import logging
import zoneinfo
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from trading_agent.configuration import agent_configuration
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.workspace import workspace_layout

_LOGGER = logging.getLogger(__name__)
_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')
_QUEUE_SIZE = 10000
_TOKENS_PER_MILLION = 1_000_000


@dataclasses.dataclass
class BackendUsage:
    """One desk's use of one backend on one day.

    Attributes:
        calls: Model calls; for Claude, turns.
        prompt_tokens: Tokens sent.
        completion_tokens: Tokens written by the model.
        cache_read_tokens: Tokens the server read from its prompt cache, for Claude and DeepSeek.
        api_equivalent_cost_usd: What Claude's usage would have cost on the API, in US dollars.
        cost_usd: What a paid API, such as DeepSeek's, actually charged, in US dollars.
    """

    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_read_tokens: int = 0
    api_equivalent_cost_usd: float = 0.0
    cost_usd: float = 0.0


class UsageTracker:
    """Today's model usage per desk and backend."""

    def __init__(
        self,
        event_bus: event_bus_module.EventBus,
        layout: workspace_layout.WorkspaceLayout,
        desk_names: Sequence[str],
        backends: Mapping[str, agent_configuration.BackendConfiguration],
        clock: Callable[[], datetime.datetime] | None = None,
    ):
        """Subscribes to the bus at once, so no usage is missed.

        Args:
            event_bus (event_bus_module.EventBus): The bus to listen to.
            layout (workspace_layout.WorkspaceLayout): Where the desks' journals are, for the replay at start.
            desk_names (Sequence[str]): The desks whose journals to replay.
            backends (Mapping[str, agent_configuration.BackendConfiguration]): The backends, for their prices.
            clock (Callable[[], datetime.datetime] | None): Returns the current time; None uses the system clock.
        """
        self._layout = layout
        self._desk_names = list(desk_names)
        self._backends = backends
        self._clock = clock
        self._started_at = self._now()
        self._usage: dict[tuple[str, str, str], BackendUsage] = {}
        self._rate_limits: dict[str, dict[str, Any]] = {}
        self._subscription = event_bus.subscribe(maximum_queued=_QUEUE_SIZE)

    async def run(self) -> None:
        """Replays today's journal, then counts new events until cancelled."""
        self.replay_today()
        try:
            while True:
                self.record(await self._subscription.next_event())
        finally:
            self._subscription.close()

    def replay_today(self) -> None:
        """Counts the usage already in today's journals, from before the tracker started."""
        day = self._started_at.date().isoformat()
        for desk_name in self._desk_names:
            path = (
                self._layout.desk_directory(desk_name)
                / 'journal'
                / f'{day}.jsonl'
            )
            if not path.is_file():
                continue
            for line in path.read_text(encoding='utf-8').splitlines():
                if '"model_usage"' not in line and '"rate_limit"' not in line:
                    continue
                try:
                    data = json.loads(line)
                    created_at = datetime.datetime.fromisoformat(
                        data['created_at']
                    )
                except ValueError, KeyError:
                    continue
                if created_at >= self._started_at:
                    continue
                self.record(
                    event_module.Event(
                        kind=event_module.EventKind(data['kind']),
                        desk=data.get('desk'),
                        payload=data.get('payload') or {},
                        created_at=created_at,
                    )
                )

    def record(self, published_event: event_module.Event) -> None:
        """Counts one event.

        Args:
            published_event (event_module.Event): The event; only model_usage and rate_limit count.
        """
        payload = published_event.payload
        if published_event.kind == event_module.EventKind.RATE_LIMIT:
            self._rate_limits[str(payload.get('backend'))] = dict(payload)
            return
        if published_event.kind != event_module.EventKind.MODEL_USAGE:
            return
        day = published_event.created_at.astimezone(_INDIA).date().isoformat()
        key = (day, str(published_event.desk), str(payload.get('backend')))
        usage = self._usage.setdefault(key, BackendUsage())
        usage.calls += 1
        usage.prompt_tokens += int(payload.get('prompt_tokens') or 0)
        usage.completion_tokens += int(payload.get('completion_tokens') or 0)
        usage.cache_read_tokens += int(payload.get('cache_read_tokens') or 0)
        usage.api_equivalent_cost_usd += float(
            payload.get('api_equivalent_cost_usd') or 0.0
        )
        usage.cost_usd += float(payload.get('cost_usd') or 0.0)

    def today(self, desk_name: str) -> dict[str, BackendUsage]:
        """A desk's usage today, by backend.

        Args:
            desk_name (str): The desk.

        Returns:
            dict[str, BackendUsage]: The usage, keyed by backend name.
        """
        day = self._now().date().isoformat()
        usage = {}
        for (
            usage_day,
            usage_desk,
            backend_name,
        ), counts in self._usage.items():
            if usage_day == day and usage_desk == desk_name:
                usage[backend_name] = counts
        return usage

    def rate_limits(self) -> dict[str, dict[str, Any]]:
        """The latest rate-limit report from each backend that sends them, such as Claude's.

        Returns:
            dict[str, dict[str, Any]]: Each report, keyed by backend name.
        """
        reports = {}
        for backend_name, status in self._rate_limits.items():
            reports[backend_name] = dict(status)
        return reports

    def summary_text(self, desk_name: str) -> str:
        """The /usage reply for a desk.

        Args:
            desk_name (str): The desk.

        Returns:
            str: Today's usage per backend, and each backend's latest limit status.
        """
        lines = [
            f"Today's model usage on desk {desk_name}:",
        ]
        usage = self.today(desk_name)
        if not usage:
            lines.append('  none yet')
        for backend_name, counts in sorted(usage.items()):
            line = f'  {backend_name}: {counts.calls} calls, {counts.prompt_tokens:,} tokens in, {counts.completion_tokens:,} out'
            if counts.cache_read_tokens:
                line = f'{line}, {counts.cache_read_tokens:,} from the cache'
            cost = self._rupees(backend_name, counts)
            if cost is not None:
                line = f'{line}, about ₹{cost:,.2f}'
            if counts.cost_usd:
                line = f'{line}, charged ${counts.cost_usd:,.4f}'
            if counts.api_equivalent_cost_usd:
                line = f'{line} (on the subscription; the API would have charged ${counts.api_equivalent_cost_usd:,.2f})'
            lines.append(line)
        for backend_name, status in sorted(self._rate_limits.items()):
            resets = status.get('resets_at')
            resets_text = ''
            if isinstance(resets, (int, float)):
                resets_text = f', resets {datetime.datetime.fromtimestamp(resets, _INDIA):%a %H:%M}'
            utilization = status.get('utilization')
            used_text = ''
            if isinstance(utilization, (int, float)):
                used_text = f', {utilization:.0%} used'
            lines.append(
                f'  {backend_name} {status.get("limit") or "subscription"} limit: {status.get("status")}{used_text}{resets_text}'
            )
        return '\n'.join(lines)

    def _rupees(self, backend_name: str, counts: BackendUsage) -> float | None:
        """The cost of a backend's usage, when its prices are configured.

        Args:
            backend_name (str): The backend.
            counts (BackendUsage): Its usage.

        Returns:
            float | None: The cost in rupees, or None without prices.
        """
        configuration = self._backends.get(backend_name)
        if configuration is None:
            return None
        prompt_price = configuration.rupees_per_million_prompt_tokens
        completion_price = configuration.rupees_per_million_completion_tokens
        if prompt_price is None or completion_price is None:
            return None
        return (
            counts.prompt_tokens * prompt_price
            + counts.completion_tokens * completion_price
        ) / _TOKENS_PER_MILLION

    def _now(self) -> datetime.datetime:
        """The current time in India.

        Returns:
            datetime.datetime: The time.
        """
        if self._clock is not None:
            return self._clock()
        return datetime.datetime.now(_INDIA)
