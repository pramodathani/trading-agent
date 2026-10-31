"""Tries a trader's backends in order, so the trader keeps working when one model is unavailable.

A backend that fails is not tried again until its waiting period ends: 30 seconds after the first failure in a row, then 1 minute, then 5 minutes. A success resets it. Each backend keeps its own conversation, so when a backend takes over it is first told what was asked and answered on the turns it missed.

With a session store, every finished exchange is also written to disk, with what each backend needs to resume. After a restart, restore_session reads them back: a backend that can resume its own conversation, such as Claude, carries on, and the others are told what they missed exactly as after a switch.

Typical usage example:

  router = ModelRouter('main', [claude_route, qwen_route, gemma_route], event_bus)
  result = await router.run_turn(trigger)
"""

import dataclasses
import datetime
import json
import time
from collections.abc import Callable, Sequence

from trading_agent.agent import context_usage as context_usage_module
from trading_agent.backends import backend as backend_module
from trading_agent.memory import session_store as session_store_module
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.runtime import turn_runner
from trading_agent.tools import tool_call_executor as tool_call_executor_module

DEFAULT_WAITING_PERIODS_SECONDS = (
    30.0,
    60.0,
    300.0,
)
_HANDOVER_EXCHANGE_LIMIT = 10
_COMPLETED_RESULT_CHARACTERS = 400


class BackendRoute:
    """One backend in a trader's order, with its failure record.

    Attributes:
        name: The backend's name in trading_agent.toml.
        turn_runner: What runs a turn on this backend.
        consecutive_failures: How many turns in a row have failed on it.
        available_at: The monotonic time from which it may be tried again.
        exchanges_seen: How many of the trader's exchanges this backend already knows about.
    """

    def __init__(self, name: str, runner: turn_runner.TurnRunner):
        """Creates a route with no failures.

        Args:
            name (str): The backend's name in trading_agent.toml.
            runner (turn_runner.TurnRunner): What runs a turn on this backend.
        """
        self.name = name
        self.turn_runner = runner
        self.consecutive_failures = 0
        self.available_at = 0.0
        self.exchanges_seen = 0

    def record_failure(
        self,
        now: float,
        waiting_periods_seconds: Sequence[float],
        retry_after_seconds: float | None = None,
    ) -> float:
        """Counts a failure and starts the backend's waiting period.

        Args:
            now (float): The current monotonic time.
            waiting_periods_seconds (Sequence[float]): The waits after the first, second and later failures in a row.
            retry_after_seconds (float | None): How long the backend itself said to wait, such as until a subscription limit resets; it replaces the usual period when given.

        Returns:
            float: How long the backend now waits, in seconds.
        """
        self.consecutive_failures += 1
        if retry_after_seconds is not None:
            waiting_seconds = max(retry_after_seconds, 0.0)
            self.available_at = now + waiting_seconds
            return waiting_seconds
        index = min(
            self.consecutive_failures - 1,
            len(waiting_periods_seconds) - 1,
        )
        waiting_seconds = waiting_periods_seconds[index]
        self.available_at = now + waiting_seconds
        return waiting_seconds

    def record_success(self) -> None:
        """Clears the failure record."""
        self.consecutive_failures = 0
        self.available_at = 0.0


class ModelRouter(turn_runner.TurnRunner):
    """Runs each turn on the first backend in the trader's order that is available.

    Attributes:
        session_id: The current session's identifier, or None without a session store or before the session starts.
        trading_date: The India date of the current session, or None likewise.
    """

    def __init__(
        self,
        trader_name: str,
        routes: Sequence[BackendRoute],
        event_bus: event_bus_module.EventBus,
        waiting_periods_seconds: Sequence[
            float
        ] = DEFAULT_WAITING_PERIODS_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        session_store: session_store_module.SessionStore | None = None,
        completed_calls: Callable[
            [str], Sequence[tool_call_executor_module.CompletedCall]
        ]
        | None = None,
    ):
        """Creates the router.

        Args:
            trader_name (str): The trader the router belongs to.
            routes (Sequence[BackendRoute]): The trader's backends, most preferred first.
            event_bus (event_bus_module.EventBus): Where failures and switches are published.
            waiting_periods_seconds (Sequence[float]): The waits after the first, second and later failures in a row.
            clock (Callable[[], float]): The source of monotonic time, replaceable in tests.
            session_store (session_store_module.SessionStore | None): Where exchanges are kept across restarts, or None to keep them in memory only.
            completed_calls (Callable[[str], Sequence[tool_call_executor_module.CompletedCall]] | None): Gives the tool calls already made for a trigger, so a backend that takes over halfway through a turn does not repeat them; None when unknown.

        Raises:
            ValueError: No routes were given.
        """
        if not routes:
            raise ValueError('A model router needs at least one backend')
        self._trader_name = trader_name
        self._routes = list(routes)
        self._event_bus = event_bus
        self._waiting_periods_seconds = waiting_periods_seconds
        self._clock = clock
        self._exchanges = []
        self._last_backend_name = None
        self._preferred_backend_name = None
        self._session_store = session_store
        self._completed_calls = completed_calls
        self.session_id: str | None = None
        self.trading_date: datetime.date | None = None

    async def run_turn(
        self,
        trigger: trigger_module.Trigger,
    ) -> turn_runner.TurnResult:
        """Runs the turn on the first available backend.

        Args:
            trigger (trigger_module.Trigger): The reason for the turn.

        Returns:
            turn_runner.TurnResult: The answer from the first backend that succeeded.

        Raises:
            backend_module.BackendUnavailableError: Every backend failed or is waiting.
        """
        reasons = []
        for route in self._ordered_routes():
            now = self._clock()
            if now < route.available_at:
                waiting = route.available_at - now
                reasons.append(f'{route.name} is waiting {waiting:.0f} s')
                continue
            attempt = self._with_handover(route, trigger)
            if reasons:
                attempt = self._with_completed_calls(attempt, reasons)
            try:
                result = await route.turn_runner.run_turn(attempt)
            except backend_module.BackendUnavailableError as error:
                waiting = route.record_failure(
                    self._clock(),
                    self._waiting_periods_seconds,
                    error.retry_after_seconds,
                )
                reasons.append(f'{route.name}: {error}')
                self._publish_unavailable(trigger, route, error, waiting)
                continue
            route.record_success()
            self._finish(trigger, route, result)
            return result
        raise backend_module.BackendUnavailableError(
            'Every backend is unavailable: ' + '; '.join(reasons)
        )

    async def side_question(self, question: str) -> tuple[str, str]:
        """Answers a side question without changing any conversation or the session's history.

        The backend that answered last is asked first, because its conversation holds the whole session; the others follow in the usual order. A failure here does not make a backend wait, because a side question must not change how turns are routed.

        Args:
            question (str): The user's question.

        Returns:
            tuple[str, str]: A tuple (backend_name, answer), where backend_name is the backend that answered.

        Raises:
            backend_module.BackendUnavailableError: Every backend failed or is waiting.
        """
        routes = []
        for route in self._routes:
            if route.name == self._last_backend_name:
                routes.append(route)
        for route in self._ordered_routes():
            if route.name != self._last_backend_name:
                routes.append(route)
        reasons = []
        for route in routes:
            now = self._clock()
            if now < route.available_at:
                waiting = route.available_at - now
                reasons.append(f'{route.name} is waiting {waiting:.0f} s')
                continue
            try:
                answer = await route.turn_runner.side_question(question)
            except backend_module.BackendUnavailableError as error:
                reasons.append(f'{route.name}: {error}')
                continue
            return route.name, answer
        raise backend_module.BackendUnavailableError(
            'Every backend is unavailable: ' + '; '.join(reasons)
        )

    async def reset(self) -> None:
        """Forgets every backend's conversation and the hand-over history, and starts a new session.

        It serves /new and the daily rollover.
        """
        for route in self._routes:
            await route.turn_runner.reset()
            route.exchanges_seen = 0
        self._exchanges = []
        self._last_backend_name = None
        self._begin_session()

    async def compact(self, trigger: trigger_module.Trigger) -> str:
        """Compacts the conversation of the backend that answered last, for /compact.

        Args:
            trigger (trigger_module.Trigger): The command's trigger, used to tag events.

        Returns:
            str: What happened, naming the backend.
        """
        route = self._ordered_routes()[0]
        for candidate in self._routes:
            if candidate.name == self._last_backend_name:
                route = candidate
        try:
            text = await route.turn_runner.compact(trigger)
        except backend_module.BackendUnavailableError as error:
            return f'{route.name} could not compact its conversation: {error}'
        return f'{route.name}: {text}'

    async def restore_session(self) -> bool:
        """Picks up the session saved before a restart, or starts the first one.

        Returns:
            bool: True when a saved session was picked up, False when a new one started.
        """
        if self._session_store is None:
            return False
        state = self._session_store.load_state()
        if state is None:
            self._begin_session()
            return False
        self.session_id = state.session_id
        self.trading_date = state.trading_date
        self._exchanges = self._session_store.exchanges(state.session_id)
        for route in self._routes:
            route.exchanges_seen = 0
            saved = state.routes.get(route.name)
            if saved is None or saved.runner_state is None:
                continue
            if await route.turn_runner.restore_state(saved.runner_state):
                route.exchanges_seen = min(
                    saved.exchanges_seen,
                    len(self._exchanges),
                )
        if self._exchanges:
            self._last_backend_name = self._exchanges[-1].backend_name
        return True

    @property
    def exchanges(self) -> tuple[session_store_module.Exchange, ...]:
        """The current session's finished exchanges, oldest first."""
        return tuple(self._exchanges)

    def context_usage(self) -> context_usage_module.ContextUsage | None:
        """How full the context window is of the backend that answered last, or of the first one to be tried before any turn.

        Returns:
            context_usage_module.ContextUsage | None: That backend's latest snapshot, or None when it has none.
        """
        chosen = self._ordered_routes()[0]
        for route in self._routes:
            if route.name == self._last_backend_name:
                chosen = route
        return chosen.turn_runner.context_usage()

    async def close(self) -> None:
        """Closes every backend's turn runner."""
        for route in self._routes:
            await route.turn_runner.close()

    @property
    def backend_names(self) -> list[str]:
        """The trader's backends in their configured order."""
        return [route.name for route in self._routes]

    @property
    def last_backend_name(self) -> str | None:
        """The backend that answered the last turn, or None before any turn."""
        return self._last_backend_name

    @property
    def preferred_backend_name(self) -> str | None:
        """The backend tried first because of /model, or None for the configured order."""
        return self._preferred_backend_name

    def choose(
        self, backend_name: str | None, model: str | None = None
    ) -> None:
        """Tries one backend first, optionally with another of its provider's models, or returns to the configured order and models.

        The chosen model applies only to the chosen backend; every other backend goes back to its configured model.

        Args:
            backend_name (str | None): The backend to try first, or None for the configured order.
            model (str | None): The model that backend should use, or None for its configured one.

        Raises:
            ValueError: No backend of the trader has that name, or a model was given without a backend.
        """
        if backend_name is None and model is not None:
            raise ValueError('Choose a backend to use another model')
        self.prefer(backend_name)
        for route in self._routes:
            if route.name == backend_name:
                route.turn_runner.use_model(model)
            else:
                route.turn_runner.use_model(None)

    def active_models(self) -> dict[str, str | None]:
        """The model each backend uses now.

        Returns:
            dict[str, str | None]: Each backend's model, keyed by backend name.
        """
        models = {}
        for route in self._routes:
            models[route.name] = route.turn_runner.active_model()
        return models

    def prefer(self, backend_name: str | None) -> None:
        """Tries one backend first from now on, or returns to the configured order.

        The other backends keep their order behind it, so they still take over when it fails.

        Args:
            backend_name (str | None): The backend to try first, or None for the configured order.

        Raises:
            ValueError: No backend of the trader has that name.
        """
        if backend_name is not None and backend_name not in self.backend_names:
            raise ValueError(
                f'No backend named {backend_name!r}; this trader has: {", ".join(self.backend_names)}'
            )
        self._preferred_backend_name = backend_name

    def set_thinking(self, level: str | None) -> None:
        """Changes the thinking level of every backend that has one, from its next turn on.

        Args:
            level (str | None): One of turn_runner.THINKING_LEVELS, or None for each backend's level in trading_agent.toml.
        """
        for route in self._routes:
            route.turn_runner.set_thinking(level)

    def thinking_lines(self) -> list[str]:
        """Describes each backend's thinking level for /think.

        Returns:
            list[str]: One line per backend, in the order they will be tried.
        """
        lines = []
        for route in self._ordered_routes():
            level = route.turn_runner.thinking()
            if level is None:
                level = 'set by the provider'
            lines.append(f'{route.name}: {level}')
        return lines

    def status_lines(self) -> list[str]:
        """Describes each backend's state for /status.

        Returns:
            list[str]: One line per backend, in the order they will be tried.
        """
        now = self._clock()
        lines = []
        for position, route in enumerate(self._ordered_routes(), start=1):
            if now < route.available_at:
                state = f'waiting {route.available_at - now:.0f} s after {route.consecutive_failures} failure(s)'
            else:
                state = 'ready'
            marker = ''
            if route.name == self._last_backend_name:
                marker = ' (answered last)'
            lines.append(f'{position}. {route.name}: {state}{marker}')
        return lines

    def _ordered_routes(self) -> list[BackendRoute]:
        """The routes in the order they will be tried.

        Returns:
            list[BackendRoute]: The preferred backend first, if one is set, then the rest in the configured order.
        """
        if self._preferred_backend_name is None:
            return list(self._routes)
        ordered = []
        for route in self._routes:
            if route.name == self._preferred_backend_name:
                ordered.append(route)
        for route in self._routes:
            if route.name != self._preferred_backend_name:
                ordered.append(route)
        return ordered

    def _with_handover(
        self,
        route: BackendRoute,
        trigger: trigger_module.Trigger,
    ) -> trigger_module.Trigger:
        """Adds the turns this backend missed to the trigger's text.

        Args:
            route (BackendRoute): The backend about to run the turn.
            trigger (trigger_module.Trigger): The original trigger.

        Returns:
            trigger_module.Trigger: The trigger unchanged, or with a hand-over in front of its text.
        """
        missed = self._exchanges[route.exchanges_seen :]
        if not missed:
            return trigger
        missed = missed[-_HANDOVER_EXCHANGE_LIMIT:]
        lines = [
            '[Hand-over: other models answered the turns below while you were unavailable. Read them for context, oldest first.]',
        ]
        for exchange in missed:
            lines.append(f'Trigger: {exchange.trigger_text}')
            lines.append(
                f'Answer from {exchange.backend_name}: {exchange.answer}'
            )
        lines.append('[End of hand-over. The new trigger follows.]')
        lines.append('')
        lines.append(trigger.text)
        return dataclasses.replace(trigger, text='\n'.join(lines))

    def _with_completed_calls(
        self,
        trigger: trigger_module.Trigger,
        reasons: Sequence[str],
    ) -> trigger_module.Trigger:
        """Adds to the trigger's text the tool calls an earlier backend already made in this turn before it failed.

        Without this, a backend taking over could repeat an action, such as placing an order a second time.

        Args:
            trigger (trigger_module.Trigger): The trigger, possibly with a hand-over already in front.
            reasons (Sequence[str]): Why the earlier backends failed.

        Returns:
            trigger_module.Trigger: The trigger unchanged when no call was made, or with the calls listed after its text.
        """
        if self._completed_calls is None:
            return trigger
        calls = self._completed_calls(trigger.trigger_id)
        if not calls:
            return trigger
        lines = [
            trigger.text,
            '',
            f'[Harness note: another model started this turn and stopped partway ({"; ".join(reasons)}). These tool calls were already made in this turn, oldest first. Do not repeat any of them unless you deliberately mean to do it again; carry on from where it stopped.]',
        ]
        for call in calls:
            outcome = 'failed' if call.is_error else 'returned'
            result = call.result_text
            if len(result) > _COMPLETED_RESULT_CHARACTERS:
                result = f'{result[:_COMPLETED_RESULT_CHARACTERS]}…'
            lines.append(
                f'- {call.name} {json.dumps(call.arguments, ensure_ascii=False)} {outcome}: {result}'
            )
        lines.append('[End of harness note.]')
        return dataclasses.replace(trigger, text='\n'.join(lines))

    def _finish(
        self,
        trigger: trigger_module.Trigger,
        route: BackendRoute,
        result: turn_runner.TurnResult,
    ) -> None:
        """Records a finished turn and publishes a switch of backend.

        Args:
            trigger (trigger_module.Trigger): The original trigger.
            route (BackendRoute): The backend that answered.
            result (turn_runner.TurnResult): Its answer.
        """
        if route.name != self._last_backend_name:
            self._publish(
                event_module.EventKind.BACKEND_SWITCH,
                {
                    'trigger_id': trigger.trigger_id,
                    'from': self._last_backend_name,
                    'to': route.name,
                },
            )
        exchange = session_store_module.Exchange(
            trigger_text=trigger.text,
            answer=result.text,
            backend_name=route.name,
            finished_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )
        self._exchanges.append(exchange)
        route.exchanges_seen = len(self._exchanges)
        self._last_backend_name = route.name
        if self._session_store is not None and self.session_id is not None:
            self._session_store.append_exchange(self.session_id, exchange)
            self._save_state()

    def _begin_session(self) -> None:
        """Starts a new session for today in the session store, if there is one."""
        if self._session_store is None:
            return
        self.trading_date = self._session_store.today()
        self.session_id = self._session_store.new_session_id(self.trading_date)
        self._save_state()

    def _save_state(self) -> None:
        """Writes which session is current and what each backend needs to resume it."""
        routes = {}
        for route in self._routes:
            routes[route.name] = session_store_module.RouteState(
                exchanges_seen=route.exchanges_seen,
                runner_state=route.turn_runner.saved_state(),
            )
        self._session_store.save_state(
            session_store_module.SessionState(
                session_id=self.session_id,
                trading_date=self.trading_date,
                routes=routes,
            )
        )

    def _publish_unavailable(
        self,
        trigger: trigger_module.Trigger,
        route: BackendRoute,
        error: backend_module.BackendUnavailableError,
        waiting_seconds: float,
    ) -> None:
        """Publishes that a backend failed and how long it will wait.

        Args:
            trigger (trigger_module.Trigger): The turn's trigger.
            route (BackendRoute): The backend that failed.
            error (backend_module.BackendUnavailableError): Why it failed.
            waiting_seconds (float): How long it now waits.
        """
        self._publish(
            event_module.EventKind.BACKEND_UNAVAILABLE,
            {
                'trigger_id': trigger.trigger_id,
                'backend': route.name,
                'reason': str(error),
                'consecutive_failures': route.consecutive_failures,
                'waiting_seconds': waiting_seconds,
            },
        )

    def _publish(self, kind: event_module.EventKind, payload: dict) -> None:
        """Publishes an event from this trader.

        Args:
            kind (event_module.EventKind): What happened.
            payload (dict): The event's details.
        """
        self._event_bus.publish(
            event_module.Event.now(kind, self._trader_name, payload)
        )
