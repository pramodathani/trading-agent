"""Asks Jev about NIFTY every 30 seconds, with no language model, and wakes the Jev traders only on a confident buy or sell.

Jev answers in under a second for a tiny fraction of a model turn's cost, so the frequent checks are Jev's, and Claude or the fallback models are only woken when there is something to act on. During the signal window on NSE trading days, each cycle:

1. skips at once when no running trader has jev_signals set;
2. asks Jev once, through the shared adviser, whatever the number of Jev traders;
3. for a buy or sell whose confidence reaches minimum_confidence, wakes each Jev trader that is idle with a message holding Jev's decision, unless that trader was woken with the same signal less than repeat_after_minutes ago;
4. for a hold, a weak signal or a failed request, wakes nobody and forgets the last signal, so the next confident signal wakes the traders again.

A trader that is running a turn, or has triggers waiting, is not woken; it is offered the signal again on the next cycle.

Typical usage example:

  watcher = JevSignalWatcher(traders, names, adviser, hours, jev_configuration)
  task = asyncio.create_task(watcher.run())
"""

import asyncio
import datetime
import logging
import zoneinfo
from collections.abc import Callable, Mapping

from trading_agent.configuration import agent_configuration
from trading_agent.risk import exchange_hours as exchange_hours_module
from trading_agent.runtime import trader_runtime as trader_runtime_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.trading import jev_adviser as jev_adviser_module

_LOGGER = logging.getLogger(__name__)
_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')
_CLOSED_SLEEP_SECONDS = 60.0
_SIGNAL_CHOICES = (
    'buy',
    'sell',
)
_HEADING = '[Jev signal from the market watcher]'


class JevSignalWatcher:
    """The model-free loop that turns Jev's confident calls into wake-ups for the Jev traders."""

    def __init__(
        self,
        traders: Mapping[str, trader_runtime_module.TraderRuntime],
        jev_trader_names: Callable[[], set[str]],
        adviser: jev_adviser_module.JevAdviser,
        hours: exchange_hours_module.ExchangeHours,
        configuration: agent_configuration.JevConfiguration,
        clock: Callable[[], datetime.datetime] | None = None,
    ):
        """Creates the watcher.

        Args:
            traders (Mapping[str, trader_runtime_module.TraderRuntime]): The running traders, keyed by name.
            jev_trader_names (Callable[[], set[str]]): Returns the names of the traders with jev_signals set.
            adviser (jev_adviser_module.JevAdviser): Reads NIFTY's state and asks Jev.
            hours (exchange_hours_module.ExchangeHours): Decides when NSE equities trade.
            configuration (agent_configuration.JevConfiguration): The interval, the confidence threshold, the repeat time and the signal window.
            clock (Callable[[], datetime.datetime] | None): Returns the current time; None uses the system clock.
        """
        self._traders = traders
        self._jev_trader_names = jev_trader_names
        self._adviser = adviser
        self._hours = hours
        self._configuration = configuration
        self._clock = clock
        self._last_signals: dict[str, tuple[str, datetime.datetime]] = {}
        window_start, window_end = configuration.signal_window.split('-')
        self._window_start = datetime.time.fromisoformat(window_start)
        self._window_end = datetime.time.fromisoformat(window_end)

    async def run(self) -> None:
        """Runs a cycle every interval while signals may wake traders, until cancelled."""
        while True:
            now = self._now()
            if not self.may_signal(now):
                await asyncio.sleep(_CLOSED_SLEEP_SECONDS)
                continue
            try:
                await self.cycle(now)
            except Exception:
                _LOGGER.exception('A Jev signal watcher cycle failed')
            await asyncio.sleep(self._configuration.interval_seconds)

    def may_signal(self, moment: datetime.datetime) -> bool:
        """Says whether NSE equities trade at a moment that falls inside the signal window.

        Args:
            moment (datetime.datetime): The moment.

        Returns:
            bool: True when a signal may wake traders now.
        """
        india_time = moment.astimezone(_INDIA).time()
        if india_time < self._window_start or india_time > self._window_end:
            return False
        nse_open, _ = self._hours.is_open(
            'nse', 'nse_equities', moment, 'exchange_hours'
        )
        return nse_open

    async def cycle(self, now: datetime.datetime) -> list[str]:
        """Asks Jev once and wakes the Jev traders that should hear its signal.

        Args:
            now (datetime.datetime): The current time.

        Returns:
            list[str]: The names of the traders woken.
        """
        names = self._running_jev_traders()
        if not names:
            return []
        try:
            advice = await self._adviser.advise()
        except jev_adviser_module.JevAdviserError as error:
            _LOGGER.warning('Jev gave no signal: %s', error)
            self._last_signals.clear()
            return []
        decision = advice.decision
        is_signal = (
            decision.choice in _SIGNAL_CHOICES
            and decision.confidence >= self._configuration.minimum_confidence
        )
        if not is_signal:
            self._last_signals.clear()
            return []
        woken = []
        for name in names:
            if self._recently_told(name, decision.choice, now):
                continue
            trader = self._traders[name]
            if self._is_busy(trader):
                continue
            trader.submit(
                trigger_module.Trigger.now(
                    trigger_module.TriggerSource.MARKET_WATCHER,
                    name,
                    self._message(advice),
                )
            )
            self._last_signals[name] = (decision.choice, now)
            woken.append(name)
        _LOGGER.info(
            'Jev said %s with confidence %.2f; woke %s',
            decision.choice,
            decision.confidence,
            woken,
        )
        return woken

    def _running_jev_traders(self) -> list[str]:
        """Lists the Jev traders that are running.

        Returns:
            list[str]: Their names, sorted.
        """
        names = []
        for name in sorted(self._jev_trader_names()):
            if name in self._traders:
                names.append(name)
        return names

    def _recently_told(
        self,
        name: str,
        choice: str,
        now: datetime.datetime,
    ) -> bool:
        """Says whether a trader was woken with the same signal within repeat_after_minutes.

        Args:
            name (str): The trader.
            choice (str): The signal now, buy or sell.
            now (datetime.datetime): The current time.

        Returns:
            bool: True when the trader should not be woken again yet.
        """
        last = self._last_signals.get(name)
        if last is None:
            return False
        last_choice, last_time = last
        if last_choice != choice:
            return False
        repeat_after = datetime.timedelta(
            minutes=self._configuration.repeat_after_minutes
        )
        return now - last_time < repeat_after

    def _is_busy(self, trader: trader_runtime_module.TraderRuntime) -> bool:
        """Says whether a trader is paused, stopped, running a turn or has triggers waiting.

        Args:
            trader (trader_runtime_module.TraderRuntime): The trader.

        Returns:
            bool: True when it should not be woken now.
        """
        if trader.paused:
            return True
        unavailable_states = (
            trader_runtime_module.TraderState.STOPPED,
            trader_runtime_module.TraderState.BUSY,
            trader_runtime_module.TraderState.WAITING,
        )
        return trader.state in unavailable_states or trader.queued_count > 0

    def _message(self, advice: jev_adviser_module.JevAdvice) -> str:
        """Writes the wake-up message.

        Args:
            advice (jev_adviser_module.JevAdvice): Jev's decision and the state it judged.

        Returns:
            str: The message.
        """
        return '\n'.join(
            [
                _HEADING,
                advice.describe(),
                'Act on it as your Persona.md says: check the entry window, your open positions and the option rules, then trade or explain why not.',
            ]
        )

    def _now(self) -> datetime.datetime:
        """The current time.

        Returns:
            datetime.datetime: Now, aware of its time zone.
        """
        if self._clock is not None:
            return self._clock()
        return datetime.datetime.now(datetime.UTC)
