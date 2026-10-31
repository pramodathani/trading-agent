"""Tests for the Jev client, the jev_decision tool, the Jev signal watcher and the jev_signals setting."""

import asyncio
import datetime
import json
import zoneinfo
from pathlib import Path
from typing import Any

import httpx
import pytest

from trading_agent.configuration import agent_configuration
from trading_agent.configuration import secrets as secrets_module
from trading_agent.doctor import doctor_check
from trading_agent.doctor.checks import jev_check
from trading_agent.runtime import trader_runtime
from trading_agent.scheduling import jev_signal_watcher
from trading_agent.tools import jev_decision_tool
from trading_agent.tools import tool
from trading_agent.trading import jev_adviser
from trading_agent.trading import jev_client
from trading_agent.workspace import workspace_layout

_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')
_TEN_IN_THE_MORNING = datetime.datetime(2026, 11, 2, 10, 0, tzinfo=_INDIA)
_STATE = {
    'instrument': 'NIFTY 50 index, NSE',
    'time_in_india': '2026-11-02 10:00:00',
    'quote': {
        'last_price': 24350.15,
    },
    'candle_interval': '5 minutes',
    'candles_oldest_first': [
        {
            'datetime': '2026-11-02 09:55:00+05:30',
            'close': 24340.0,
        },
    ],
}


def _answer(choice: str, confidence: float) -> dict[str, Any]:
    """Builds an answer shaped like Jev's.

    Args:
        choice (str): The chosen answer.
        confidence (float): Its confidence.

    Returns:
        dict[str, Any]: The decoded JSON answer.
    """
    return {
        'model': 'jev-1.14.0',
        'answers': {
            'direction': {
                'type': 'choice',
                'choice': choice,
                'confidence': confidence,
                'probabilities': {
                    'buy': 0.7,
                    'sell': 0.1,
                    'hold': 0.2,
                },
            },
        },
        'usage': {
            'input_tokens': 400,
            'output_tokens': 10,
        },
    }


class _RecordingHandler:
    """Answers Jev requests with a fixed reply and keeps every request.

    Attributes:
        requests: The requests received.
        status_code: The HTTP status to answer with.
        payload: The JSON to answer with.
    """

    def __init__(self, status_code: int, payload: Any):
        """Creates the handler.

        Args:
            status_code (int): The HTTP status to answer with.
            payload (Any): The JSON to answer with.
        """
        self.requests = []
        self.status_code = status_code
        self.payload = payload

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Records a request and answers it.

        Args:
            request (httpx.Request): The request.

        Returns:
            httpx.Response: The fixed reply.
        """
        self.requests.append(request)
        return httpx.Response(self.status_code, json=self.payload)


def _client(handler: _RecordingHandler) -> jev_client.JevClient:
    """Builds a client that talks to a handler instead of TypeSafe.

    Args:
        handler (_RecordingHandler): The stand-in for the API.

    Returns:
        jev_client.JevClient: The client.
    """
    return jev_client.JevClient(
        agent_configuration.JevConfiguration(),
        'test-key',
        transport=httpx.MockTransport(handler),
    )


class _FakeMarketState:
    """Stands in for the NIFTY state reader."""

    async def read(self) -> dict[str, Any]:
        """Returns a fixed state.

        Returns:
            dict[str, Any]: The state.
        """
        return _STATE


class _FakeAdviser:
    """Stands in for the adviser, returning set decisions in turn.

    Attributes:
        decisions: The decisions still to return, or an error to raise.
        calls: How many times it was asked.
    """

    def __init__(self, decisions: list[Any]):
        """Creates the adviser.

        Args:
            decisions (list[Any]): Each one is a (choice, confidence) tuple, or an exception to raise.
        """
        self.decisions = decisions
        self.calls = 0

    async def advise(self) -> jev_adviser.JevAdvice:
        """Returns the next decision.

        Returns:
            jev_adviser.JevAdvice: The decision with the fixed state.

        Raises:
            Exception: The next item is an exception.
        """
        self.calls += 1
        item = self.decisions.pop(0)
        if isinstance(item, Exception):
            raise item
        choice, confidence = item
        decision = jev_client.JevDecision(
            choice=choice,
            confidence=confidence,
            probabilities={
                'buy': 0.7,
                'sell': 0.1,
                'hold': 0.2,
            },
            model='jev-1.14.0',
        )
        return jev_adviser.JevAdvice(decision=decision, state=_STATE)


class _FakeTrader:
    """Stands in for a running trader.

    Attributes:
        state: The trader's state.
        paused: Whether the trader is paused.
        queued_count: How many triggers are waiting.
        submitted: The triggers it received.
    """

    def __init__(self):
        """Creates an idle trader."""
        self.state = trader_runtime.TraderState.IDLE
        self.paused = False
        self.queued_count = 0
        self.submitted = []

    def submit(self, trigger: Any) -> None:
        """Records a trigger.

        Args:
            trigger (Any): The trigger.
        """
        self.submitted.append(trigger)


class _OpenHours:
    """Stands in for exchange hours that are always open."""

    def is_open(
        self,
        exchange: str,
        segment: str,
        moment: datetime.datetime,
        trading_window: str,
    ) -> tuple[bool, str]:
        """Says the exchange is open.

        Args:
            exchange (str): Ignored.
            segment (str): Ignored.
            moment (datetime.datetime): Ignored.
            trading_window (str): Ignored.

        Returns:
            tuple[bool, str]: Always (True, '').
        """
        del exchange, segment, moment, trading_window
        return True, ''


def _watcher(
    adviser: _FakeAdviser,
    traders: dict[str, _FakeTrader],
) -> jev_signal_watcher.JevSignalWatcher:
    """Builds a watcher over fakes, with every trader a Jev trader.

    Args:
        adviser (_FakeAdviser): The stand-in adviser.
        traders (dict[str, _FakeTrader]): The stand-in traders.

    Returns:
        jev_signal_watcher.JevSignalWatcher: The watcher.
    """
    return jev_signal_watcher.JevSignalWatcher(
        traders,
        lambda: set(traders),
        adviser,
        _OpenHours(),
        agent_configuration.JevConfiguration(),
    )


def test_decide_sends_one_choice_question_and_reads_the_answer():
    """The client posts the state with buy, sell and hold, and reads Jev's choice."""
    handler = _RecordingHandler(200, _answer('buy', 0.72))
    decision = asyncio.run(_client(handler).decide(_STATE))
    request = handler.requests[0]
    body = json.loads(request.content)
    assert str(request.url) == 'https://api.typesafe.ai/v1/systemone'
    assert request.headers['authorization'] == 'Bearer test-key'
    assert body['model'] == 'jev-latest'
    assert body['state'] == _STATE
    assert body['questions']['direction']['type'] == 'choice'
    assert set(body['questions']['direction']['criteria']) == {
        'buy',
        'sell',
        'hold',
    }
    assert decision.choice == 'buy'
    assert decision.confidence == 0.72
    assert decision.probabilities['hold'] == 0.2
    assert decision.model == 'jev-1.14.0'


def test_decide_raises_on_a_refused_request():
    """An HTTP error from Jev becomes a JevError that names the status."""
    handler = _RecordingHandler(401, {'error': 'bad key'})
    with pytest.raises(jev_client.JevError, match='HTTP 401'):
        asyncio.run(_client(handler).decide(_STATE))


def test_decide_raises_on_an_unknown_choice():
    """A choice outside buy, sell and hold is refused."""
    handler = _RecordingHandler(200, _answer('short', 0.9))
    with pytest.raises(jev_client.JevError, match='unknown answer'):
        asyncio.run(_client(handler).decide(_STATE))


def test_tool_describes_the_decision():
    """jev_decision returns the choice, the confidence and the price Jev judged."""
    handler = _RecordingHandler(200, _answer('sell', 0.65))
    adviser = jev_adviser.JevAdviser(_FakeMarketState(), _client(handler))
    result = asyncio.run(
        jev_decision_tool.JevDecisionTool(adviser).run(tool.NoArguments())
    )
    assert not result.is_error
    assert 'says SELL with confidence 0.65' in result.text
    assert '24,350.15' in result.text


def test_tool_reports_a_failure_as_hold():
    """When Jev fails, the tool says to treat the moment as hold."""
    handler = _RecordingHandler(500, {'error': 'down'})
    adviser = jev_adviser.JevAdviser(_FakeMarketState(), _client(handler))
    result = asyncio.run(
        jev_decision_tool.JevDecisionTool(adviser).run(tool.NoArguments())
    )
    assert result.is_error
    assert 'Treat this as hold' in result.text


def test_watcher_wakes_on_a_confident_buy_only_once():
    """A confident buy wakes the trader, and the same buy a cycle later does not."""
    adviser = _FakeAdviser(
        [
            ('buy', 0.8),
            ('buy', 0.8),
        ]
    )
    trader = _FakeTrader()
    watcher = _watcher(adviser, {'jev-scalper': trader})
    first = asyncio.run(watcher.cycle(_TEN_IN_THE_MORNING))
    later = _TEN_IN_THE_MORNING + datetime.timedelta(seconds=30)
    second = asyncio.run(watcher.cycle(later))
    assert first == ['jev-scalper']
    assert not second
    assert len(trader.submitted) == 1
    assert 'says BUY' in trader.submitted[0].text


def test_watcher_repeats_a_signal_after_the_repeat_time():
    """The same signal wakes the trader again once repeat_after_minutes has passed."""
    adviser = _FakeAdviser(
        [
            ('sell', 0.9),
            ('sell', 0.9),
        ]
    )
    trader = _FakeTrader()
    watcher = _watcher(adviser, {'jev-scalper': trader})
    asyncio.run(watcher.cycle(_TEN_IN_THE_MORNING))
    later = _TEN_IN_THE_MORNING + datetime.timedelta(minutes=6)
    asyncio.run(watcher.cycle(later))
    assert len(trader.submitted) == 2


def test_watcher_ignores_hold_and_weak_signals():
    """A hold, or a buy below the confidence threshold, wakes nobody."""
    adviser = _FakeAdviser(
        [
            ('hold', 0.95),
            ('buy', 0.4),
        ]
    )
    trader = _FakeTrader()
    watcher = _watcher(adviser, {'jev-scalper': trader})
    asyncio.run(watcher.cycle(_TEN_IN_THE_MORNING))
    asyncio.run(watcher.cycle(_TEN_IN_THE_MORNING))
    assert not trader.submitted


def test_watcher_wakes_again_after_a_hold():
    """A hold in between makes the next confident buy wake the trader again."""
    adviser = _FakeAdviser(
        [
            ('buy', 0.8),
            ('hold', 0.8),
            ('buy', 0.8),
        ]
    )
    trader = _FakeTrader()
    watcher = _watcher(adviser, {'jev-scalper': trader})
    for seconds in (0, 30, 60):
        moment = _TEN_IN_THE_MORNING + datetime.timedelta(seconds=seconds)
        asyncio.run(watcher.cycle(moment))
    assert len(trader.submitted) == 2


def test_watcher_leaves_a_busy_trader_alone_and_retries():
    """A busy trader is not woken, and hears the signal on the next cycle once idle."""
    adviser = _FakeAdviser(
        [
            ('buy', 0.8),
            ('buy', 0.8),
        ]
    )
    trader = _FakeTrader()
    trader.state = trader_runtime.TraderState.BUSY
    watcher = _watcher(adviser, {'jev-scalper': trader})
    asyncio.run(watcher.cycle(_TEN_IN_THE_MORNING))
    trader.state = trader_runtime.TraderState.IDLE
    later = _TEN_IN_THE_MORNING + datetime.timedelta(seconds=30)
    asyncio.run(watcher.cycle(later))
    assert len(trader.submitted) == 1


def test_watcher_never_wakes_a_paused_trader():
    """A paused trader is not woken, so its chat does not fill with paused replies."""
    adviser = _FakeAdviser(
        [
            ('buy', 0.8),
        ]
    )
    trader = _FakeTrader()
    trader.paused = True
    watcher = _watcher(adviser, {'jev-scalper': trader})
    asyncio.run(watcher.cycle(_TEN_IN_THE_MORNING))
    assert not trader.submitted


def test_watcher_does_not_ask_jev_without_jev_traders():
    """With no Jev trader running, Jev is never asked."""
    adviser = _FakeAdviser([])
    watcher = _watcher(adviser, {})
    asyncio.run(watcher.cycle(_TEN_IN_THE_MORNING))
    assert adviser.calls == 0


def test_watcher_survives_a_failed_request():
    """A failed request wakes nobody and raises nothing."""
    adviser = _FakeAdviser(
        [
            jev_adviser.JevAdviserError('Jev could not be reached'),
        ]
    )
    trader = _FakeTrader()
    watcher = _watcher(adviser, {'jev-scalper': trader})
    woken = asyncio.run(watcher.cycle(_TEN_IN_THE_MORNING))
    assert not woken
    assert not trader.submitted


def test_watcher_stays_quiet_outside_the_signal_window():
    """Before 09:30 and after 14:45 India time, the watcher may not signal."""
    watcher = _watcher(_FakeAdviser([]), {})
    early = datetime.datetime(2026, 11, 2, 9, 20, tzinfo=_INDIA)
    late = datetime.datetime(2026, 11, 2, 14, 50, tzinfo=_INDIA)
    assert not watcher.may_signal(early)
    assert not watcher.may_signal(late)
    assert watcher.may_signal(_TEN_IN_THE_MORNING)


def test_trader_configuration_reads_jev_signals():
    """trader.toml may set jev_signals, and it is off by default."""
    with_jev = agent_configuration.TraderConfiguration(
        name='jev-scalper',
        jev_signals=True,
    )
    without_jev = agent_configuration.TraderConfiguration(name='scalper')
    assert with_jev.jev_signals
    assert not without_jev.jev_signals


def _layout_with_jev_trader(
    workspace: Path,
) -> workspace_layout.WorkspaceLayout:
    """Builds a workspace with one trader that sets jev_signals.

    Args:
        workspace (Path): An empty folder.

    Returns:
        workspace_layout.WorkspaceLayout: The layout of the workspace.
    """
    layout = workspace_layout.WorkspaceLayout(workspace)
    trader_directory = layout.trader_directory('jev-scalper')
    trader_directory.mkdir(parents=True)
    (trader_directory / 'trader.toml').write_text(
        'name = "jev-scalper"\njev_signals = true\n',
        encoding='utf-8',
    )
    return layout


def test_doctor_passes_without_jev_traders(tmp_path: Path):
    """With no key and no Jev trader, the doctor has nothing to check."""
    check = jev_check.JevCheck(
        agent_configuration.JevConfiguration(),
        secrets_module.Secrets(_env_file=None, typesafe_api_key=''),
        workspace_layout.WorkspaceLayout(tmp_path),
        [],
    )
    assert check.run().status == doctor_check.CheckStatus.OK


def test_doctor_fails_a_jev_trader_without_a_key(tmp_path: Path):
    """A trader with jev_signals and no TypeSafe key fails the check."""
    check = jev_check.JevCheck(
        agent_configuration.JevConfiguration(),
        secrets_module.Secrets(_env_file=None, typesafe_api_key=''),
        _layout_with_jev_trader(tmp_path),
        [
            'jev-scalper',
        ],
    )
    result = check.run()
    assert result.status == doctor_check.CheckStatus.FAILED
    assert 'TRADING_AGENT_TYPESAFE_API_KEY' in result.message
