"""Tests for the market watcher, price alerts, the webhook route and the usage tracker."""

import asyncio
import datetime
import json
import zoneinfo
from pathlib import Path
from typing import Any

import fastapi
import fastapi.testclient

from trading_agent.configuration import agent_configuration
from trading_agent.gateway.routes import webhook_routes
from trading_agent.journal import usage_tracker
from trading_agent.risk import exchange_hours
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.scheduling import market_watcher
from trading_agent.scheduling import price_alert_store
from trading_agent.tools import set_price_alert_tool
from trading_agent.trading import desk_order_book
from trading_agent.workspace import workspace_layout

_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')


class _FakeDesk:
    """Stands in for a running desk.

    Attributes:
        name: The desk's name.
        submitted: The triggers it received.
    """

    def __init__(self, name: str = 'main'):
        """Creates the desk.

        Args:
            name (str): Its name.
        """
        self.name = name
        self.submitted = []

    def submit(self, trigger: trigger_module.Trigger) -> None:
        """Records a trigger.

        Args:
            trigger (trigger_module.Trigger): The trigger.
        """
        self.submitted.append(trigger)


class _FakeInstrument:
    """Stands in for a tradeable instrument.

    Attributes:
        instrument_id: UBI's id.
        exchange: The exchange.
        segment: The segment.
        symbol: The symbol.
        underlying_symbol: Empty for a share.
        last_price: The last traded price.
    """

    def __init__(self, last_price: float):
        """Creates IDEA at a price.

        Args:
            last_price (float): The price.
        """
        self.instrument_id = 'idea-id'
        self.exchange = 'nse'
        self.segment = 'nse_equities'
        self.symbol = 'IDEA'
        self.underlying_symbol = None
        self.last_price = last_price


class _FakeReader:
    """Stands in for the broker reader.

    Attributes:
        orders: The order book's orders.
        last_price: IDEA's price.
        order_book_reads: How many times the order book was read.
    """

    def __init__(self):
        """Creates the reader with an empty order book."""
        self.orders = []
        self.last_price = 12.30
        self.order_book_reads = 0

    async def call(self, work: Any) -> Any:
        """Runs the work at once.

        Args:
            work (Any): The callable.

        Returns:
            Any: Its result.
        """
        return work()

    def get(self, path: str, parameters: dict | None = None) -> dict[str, Any]:
        """Returns the order book.

        Args:
            path (str): The API path, the order book's.
            parameters (dict | None): Ignored.

        Returns:
            dict[str, Any]: The book.
        """
        del path, parameters
        self.order_book_reads += 1
        return {
            'orders': self.orders,
        }

    def tradeable_instrument(self, arguments: object) -> _FakeInstrument:
        """Returns IDEA.

        Args:
            arguments (object): Ignored.

        Returns:
            _FakeInstrument: IDEA at the current price.
        """
        del arguments
        return _FakeInstrument(self.last_price)


class _FakeRiskEngine:
    """Counts account checks.

    Attributes:
        checks: How many times check_account ran.
    """

    def __init__(self):
        """Creates the engine."""
        self.checks = 0

    async def check_account(self) -> None:
        """Counts a check."""
        self.checks += 1


class _Setup:
    """A watcher over one desk with a real order book and alert store.

    Attributes:
        desk: The fake desk.
        reader: The fake reader.
        risk_engine: The fake risk engine.
        order_book: The desk order book.
        alerts: The desk's alerts.
        state_file: The watcher's state file.
        event_bus: The bus.
    """

    def __init__(self, tmp_path: Path):
        """Builds the parts.

        Args:
            tmp_path (Path): A scratch folder.
        """
        self.desk = _FakeDesk()
        self.reader = _FakeReader()
        self.risk_engine = _FakeRiskEngine()
        self.order_book = desk_order_book.DeskOrderBook(tmp_path / 'orders.db')
        self.alerts = price_alert_store.PriceAlertStore(
            tmp_path / 'alerts.json'
        )
        self.state_file = tmp_path / 'watcher.json'
        self.event_bus = event_bus_module.EventBus()

    def watcher(self) -> market_watcher.MarketWatcher:
        """Builds a watcher, as the gateway would at start.

        Returns:
            market_watcher.MarketWatcher: The watcher.
        """
        return market_watcher.MarketWatcher(
            {
                'main': self.desk,
            },
            {
                'main': self.alerts,
            },
            self.order_book,
            self.reader,
            self.risk_engine,
            exchange_hours.ExchangeHours(),
            self.event_bus,
            self.state_file,
        )

    def add_order(self, parent_id: str, dry_run: bool = False) -> None:
        """Records one desk order.

        Args:
            parent_id (str): Its parent id.
            dry_run (bool): Whether it was a dry run.
        """
        self.order_book.add(
            desk_order_book.OrderRecord(
                record_id=parent_id,
                desk='main',
                kind='order',
                parent_id=parent_id,
                order_id=None,
                instrument_id='idea-id',
                exchange='nse',
                segment='nse_equities',
                symbol='IDEA',
                transaction_type='buy',
                quantity=1,
                product='cnc',
                price=12.21,
                dry_run=dry_run,
                state=desk_order_book.OPEN,
                placed_at=desk_order_book.DeskOrderBook.now_text(),
            )
        )


class TestFills:
    """Finished broker orders are reported once to the desk that placed them."""

    def test_fill_is_reported_once_even_after_a_restart(
        self, tmp_path: Path
    ) -> None:
        """The desk's complete order is reported; another desk's is not; a new watcher does not repeat it.

        Args:
            tmp_path (Path): A scratch folder.
        """
        setup = _Setup(tmp_path)
        setup.add_order('P1')
        setup.reader.orders = [
            {
                'order_id': '9001',
                'engine_parent_id': 'P1',
                'status': 'COMPLETE',
                'filled_quantity': 1,
                'average_price': 12.21,
            },
            {
                'order_id': '9002',
                'engine_parent_id': 'P1',
                'status': 'OPEN',
            },
            {
                'order_id': '9003',
                'engine_parent_id': 'someone-else',
                'status': 'COMPLETE',
            },
        ]
        assert asyncio.run(setup.watcher().check_fills()) == 1
        assert asyncio.run(setup.watcher().check_fills()) == 0
        text = setup.desk.submitted[0].text
        assert text == (
            '[Order update from the market watcher]\n'
            '- Order 9001 of your order buy 1 IDEA (parent_id P1): COMPLETE, 1 filled at an average of 12.21.'
        )
        assert (
            setup.desk.submitted[0].source
            == trigger_module.TriggerSource.MARKET_WATCHER
        )

    def test_no_real_orders_means_no_order_book_read(
        self, tmp_path: Path
    ) -> None:
        """With only a dry-run order open, UBI is not asked for the order book.

        Args:
            tmp_path (Path): A scratch folder.
        """
        setup = _Setup(tmp_path)
        setup.add_order('dry-1', dry_run=True)
        asyncio.run(setup.watcher().check_fills())
        assert setup.reader.order_book_reads == 0


class TestPriceAlerts:
    """Alerts fire once when crossed, and cannot be set already crossed."""

    def test_crossed_alert_wakes_the_desk_and_is_removed(
        self, tmp_path: Path
    ) -> None:
        """IDEA at 12.30 crosses "above 12.25" but not "below 12.00".

        Args:
            tmp_path (Path): A scratch folder.
        """
        setup = _Setup(tmp_path)
        for condition, price in (('above', 12.25), ('below', 12.00)):
            setup.alerts.add(
                price_alert_store.PriceAlert.new(
                    instrument_id='idea-id',
                    exchange='nse',
                    segment='nse_equities',
                    symbol='IDEA',
                    condition=condition,
                    price=price,
                    note='sell half' if condition == 'above' else '',
                )
            )
        assert asyncio.run(setup.watcher().check_alerts()) == 1
        assert [alert.condition for alert in setup.alerts.alerts()] == [
            'below',
        ]
        assert setup.desk.submitted[0].text == (
            '[Price alert from the market watcher]\n'
            '- IDEA traded at 12.30, above your alert at 12.25. Your note: sell half'
        )

    def test_tool_refuses_an_alert_that_is_already_crossed(
        self, tmp_path: Path
    ) -> None:
        """Below 12.50 with IDEA at 12.30 is refused; above 12.50 is set.

        Args:
            tmp_path (Path): A scratch folder.
        """
        setup = _Setup(tmp_path)
        tool = set_price_alert_tool.SetPriceAlertTool(
            setup.reader, setup.alerts
        )
        refused = asyncio.run(
            tool.run(
                set_price_alert_tool.SetPriceAlertArguments(
                    exchange='nse',
                    segment='equities',
                    symbol='IDEA',
                    condition='below',
                    price=12.50,
                )
            )
        )
        assert refused.is_error
        assert 'would fire at once' in refused.text
        accepted = asyncio.run(
            tool.run(
                set_price_alert_tool.SetPriceAlertArguments(
                    exchange='nse',
                    segment='equities',
                    symbol='IDEA',
                    condition='above',
                    price=12.50,
                    note='take profit',
                )
            )
        )
        assert 'set: IDEA above 12.50 (take profit)' in accepted.text


class TestWatcherCycle:
    """The cycle checks the account once a minute and only while the market is open."""

    def test_account_check_is_paced_and_market_hours_apply(
        self, tmp_path: Path
    ) -> None:
        """Two cycles 15 seconds apart check the account once; Saturday is closed and Monday 10:00 open.

        Args:
            tmp_path (Path): A scratch folder.
        """
        setup = _Setup(tmp_path)
        watcher = setup.watcher()
        start = datetime.datetime(2026, 10, 19, 10, 0, tzinfo=_INDIA)
        asyncio.run(watcher.cycle(start))
        asyncio.run(watcher.cycle(start + datetime.timedelta(seconds=15)))
        asyncio.run(watcher.cycle(start + datetime.timedelta(seconds=61)))
        assert setup.risk_engine.checks == 2
        assert watcher.market_open(start)
        assert not watcher.market_open(
            datetime.datetime(2026, 10, 17, 10, 0, tzinfo=_INDIA)
        )


class TestWebhook:
    """The webhook wakes a desk only with the right token."""

    def test_token_desk_and_body_handling(self) -> None:
        """No token configured means 404; a wrong token 401; the right one queues the JSON text."""
        desk = _FakeDesk()
        application = fastapi.FastAPI()
        application.include_router(
            webhook_routes.WebhookRoutes({'main': desk}, 'hook-secret').router()
        )
        client = fastapi.testclient.TestClient(application)
        assert (
            client.post('/hooks/wake/main?token=nope', content='hi').status_code
            == 401
        )
        assert (
            client.post(
                '/hooks/wake/other?token=hook-secret', content='hi'
            ).status_code
            == 404
        )
        answer = client.post(
            '/hooks/wake/main?token=hook-secret',
            content=json.dumps({'text': 'NIFTY crossed 24,000'}),
        )
        assert answer.status_code == 202
        header = client.post(
            '/hooks/wake/main',
            content='plain text alert',
            headers={'X-Webhook-Token': 'hook-secret'},
        )
        assert header.status_code == 202
        assert desk.submitted[0].source == trigger_module.TriggerSource.WEBHOOK
        assert desk.submitted[0].text.endswith('\nNIFTY crossed 24,000')
        assert desk.submitted[1].text.endswith('\nplain text alert')
        disabled = fastapi.FastAPI()
        disabled.include_router(
            webhook_routes.WebhookRoutes({'main': desk}, '').router()
        )
        assert (
            fastapi.testclient.TestClient(disabled)
            .post('/hooks/wake/main', content='x')
            .status_code
            == 404
        )


class TestUsageTracker:
    """Usage is counted per desk and backend, priced, and survives a restart."""

    def test_counts_costs_limits_and_replay(self, tmp_path: Path) -> None:
        """A journal line from before the start and two live events are counted; OpenAI is priced; Claude's limit is shown.

        Args:
            tmp_path (Path): A scratch folder.
        """
        start = datetime.datetime(2026, 10, 19, 11, 0, tzinfo=_INDIA)
        layout = workspace_layout.WorkspaceLayout(tmp_path)
        journal = layout.desk_directory('main') / 'journal'
        journal.mkdir(parents=True)
        earlier = {
            'kind': 'model_usage',
            'desk': 'main',
            'payload': {
                'backend': 'claude',
                'prompt_tokens': 100,
                'completion_tokens': 50,
                'cache_read_tokens': 900,
                'api_equivalent_cost_usd': 0.25,
            },
            'created_at': (start - datetime.timedelta(hours=1)).isoformat(),
        }
        (journal / '2026-10-19.jsonl').write_text(
            json.dumps(earlier) + '\n', encoding='utf-8'
        )
        backends = {
            'openai': agent_configuration.BackendConfiguration(
                kind='openai_compatible',
                base_url='https://api.openai.com/v1',
                model='gpt-x',
                context_window=128000,
                rupees_per_million_prompt_tokens=100.0,
                rupees_per_million_completion_tokens=400.0,
            ),
        }
        tracker = usage_tracker.UsageTracker(
            event_bus_module.EventBus(),
            layout,
            [
                'main',
            ],
            backends,
            clock=lambda: start,
        )
        tracker.replay_today()
        tracker.record(
            event_module.Event(
                kind=event_module.EventKind.MODEL_USAGE,
                desk='main',
                payload={
                    'backend': 'openai',
                    'prompt_tokens': 10000,
                    'completion_tokens': 5000,
                },
                created_at=start,
            )
        )
        tracker.record(
            event_module.Event(
                kind=event_module.EventKind.RATE_LIMIT,
                desk='main',
                payload={
                    'backend': 'claude',
                    'status': 'allowed_warning',
                    'limit': 'five_hour',
                    'utilization': 0.82,
                },
                created_at=start,
            )
        )
        text = tracker.summary_text('main')
        assert (
            '  claude: 1 calls, 100 tokens in, 50 out, 900 from the cache (on the subscription; the API would have charged $0.25)'
            in text
        )
        assert (
            '  openai: 1 calls, 10,000 tokens in, 5,000 out, about ₹3.00'
            in text
        )
        assert '  claude five_hour limit: allowed_warning, 82% used' in text
