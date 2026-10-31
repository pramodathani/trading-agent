"""Tests for the order tools, with a fake UBI and a fake risk engine."""

import asyncio
import datetime
from pathlib import Path
from typing import Any

import pydantic
import pytest
from tradingmachine.unified_broker_interface import exceptions as ubi_exceptions

from trading_agent.risk import account_snapshot
from trading_agent.risk import order_request
from trading_agent.risk import risk_engine
from trading_agent.risk import risk_ledger
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.tools import cancel_order_tool
from trading_agent.tools import flatten_trader_tool
from trading_agent.tools import modify_order_tool
from trading_agent.tools import order_tool
from trading_agent.tools import place_bracket_order_tool
from trading_agent.tools import place_order_tool
from trading_agent.trading import order_arguments
from trading_agent.trading import result_formatter
from trading_agent.trading import trader_order_book

_INFY_ID = 'infy-id'
_NIFTY_FUTURE_ID = 'nifty-future-id'


class _FakeInstrument:
    """Stands in for a tradingmachine TradeableInstrument, recording each request.

    Attributes:
        instrument_id: UBI's id.
        exchange: The exchange.
        segment: The segment.
        symbol: The symbol.
        underlying_symbol: The underlying's symbol.
        lot_size: Units per lot.
        last_price: The last traded price.
        requests: Each (method name, keyword arguments) received.
    """

    def __init__(
        self,
        instrument_id: str,
        segment: str,
        symbol: str | None,
        lot_size: int,
        last_price: float | None,
        answer: dict[str, Any],
        failure: Exception | None = None,
    ):
        """Creates the instrument.

        Args:
            instrument_id (str): UBI's id.
            segment (str): The segment.
            symbol (str | None): The symbol, or None for a derivative.
            lot_size (int): Units per lot.
            last_price (float | None): The last traded price.
            answer (dict[str, Any]): What every request returns.
            failure (Exception | None): An exception every request raises instead, or None.
        """
        self.instrument_id = instrument_id
        self.exchange = 'nse'
        self.segment = segment
        self.symbol = symbol
        self.underlying_symbol = 'NIFTY'
        self.lot_size = lot_size
        self.last_price = last_price
        self.requests = []
        self._answer = answer
        self._failure = failure

    def place_order(self, **keyword_arguments: Any) -> dict[str, Any]:
        """Records an order.

        Args:
            **keyword_arguments (Any): The order.

        Returns:
            dict[str, Any]: The configured answer.
        """
        return self._respond('place_order', keyword_arguments)

    def modify_order(self, **keyword_arguments: Any) -> dict[str, Any]:
        """Records a change.

        Args:
            **keyword_arguments (Any): The change.

        Returns:
            dict[str, Any]: The configured answer.
        """
        return self._respond('modify_order', keyword_arguments)

    def cancel_parent(
        self, parent_id: str, part: str | None = None, dry_run: bool = False
    ) -> dict[str, Any]:
        """Records a cancellation through the engine.

        Args:
            parent_id (str): The parent.
            part (str | None): One part, or None.
            dry_run (bool): Whether it is a dry run.

        Returns:
            dict[str, Any]: The configured answer.
        """
        return self._respond(
            'cancel_parent',
            {
                'parent_id': parent_id,
                'part': part,
                'dry_run': dry_run,
            },
        )

    def cancel_order(
        self, order_id: str, dry_run: bool = False
    ) -> dict[str, Any]:
        """Records a cancellation at a broker.

        Args:
            order_id (str): The broker's id.
            dry_run (bool): Whether it is a dry run.

        Returns:
            dict[str, Any]: The configured answer.
        """
        return self._respond(
            'cancel_order',
            {
                'order_id': order_id,
                'dry_run': dry_run,
            },
        )

    def _respond(
        self, method: str, keyword_arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Records a request and answers it.

        Args:
            method (str): The method called.
            keyword_arguments (dict[str, Any]): Its arguments.

        Returns:
            dict[str, Any]: The configured answer.

        Raises:
            Exception: The configured failure.
        """
        self.requests.append((method, keyword_arguments))
        if self._failure is not None:
            raise self._failure
        return self._answer


class _FakeReader:
    """Stands in for BrokerReader, handing out fake instruments by id."""

    def __init__(self, instruments_by_id: dict[str, _FakeInstrument]):
        """Creates the reader.

        Args:
            instruments_by_id (dict[str, _FakeInstrument]): The instruments, by id; a lookup by symbol returns the first.
        """
        self._instruments = instruments_by_id

    async def call(self, work):
        """Runs the work at once.

        Args:
            work (Callable): The work.

        Returns:
            object: What the work returned.
        """
        return work()

    def tradeable_instrument(self, arguments) -> _FakeInstrument:
        """Finds a fake instrument.

        Args:
            arguments (InstrumentArguments): How the instrument was named.

        Returns:
            _FakeInstrument: The instrument.
        """
        if arguments.instrument_id is not None:
            return self._instruments[arguments.instrument_id]
        for instrument in self._instruments.values():
            return instrument
        raise KeyError('no instrument')


class _FakeEngine:
    """Stands in for the risk engine, approving or refusing every order.

    Attributes:
        requests: Every order it was asked about.
    """

    def __init__(self, reasons: tuple[str, ...] = ()):
        """Creates the engine.

        Args:
            reasons (tuple[str, ...]): The reasons to refuse with; empty to approve.
        """
        self._reasons = reasons
        self.requests = []

    async def evaluate(
        self, request: order_request.OrderRequest
    ) -> risk_engine.RiskDecision:
        """Answers with the configured decision.

        Args:
            request (order_request.OrderRequest): The order.

        Returns:
            risk_engine.RiskDecision: The decision.
        """
        self.requests.append(request)
        return risk_engine.RiskDecision(
            approved=not self._reasons,
            reasons=self._reasons,
            estimated_margin=1234.5,
        )


class _FakeSnapshotReader:
    """Stands in for AccountSnapshotReader."""

    def __init__(self, snapshot: account_snapshot.AccountSnapshot):
        """Creates the reader.

        Args:
            snapshot (account_snapshot.AccountSnapshot): What it reads.
        """
        self._snapshot = snapshot

    async def read(self) -> account_snapshot.AccountSnapshot:
        """Returns the snapshot.

        Returns:
            account_snapshot.AccountSnapshot: The snapshot.
        """
        return self._snapshot


class _Setup:
    """Order services built from fakes, with a subscription to the bus.

    Attributes:
        share: A fake INFY share.
        future: A fake NIFTY future with a lot of 75.
        engine: The fake risk engine.
        order_book: A real trader order book in a temporary folder.
        ledger: A real risk ledger in a temporary folder.
        subscription: A subscription to every event.
        services: The services the tools use.
    """

    def __init__(
        self,
        tmp_path: Path,
        answer: dict[str, Any] | None = None,
        reasons: tuple[str, ...] = (),
        failure: Exception | None = None,
        positions: tuple[account_snapshot.PositionRow, ...] = (),
    ):
        """Builds the services.

        Args:
            tmp_path (Path): A temporary folder from pytest.
            answer (dict[str, Any] | None): What UBI answers, or None for a dry-run answer.
            reasons (tuple[str, ...]): Reasons for the engine to refuse with; empty to approve.
            failure (Exception | None): An exception UBI raises, or None.
            positions (tuple[account_snapshot.PositionRow, ...]): The account's positions.
        """
        if answer is None:
            answer = {
                'dry_run': True,
                'request': {
                    'quantity': 10,
                },
            }
        self.share = _FakeInstrument(
            _INFY_ID,
            'nse_equities',
            'INFY',
            1,
            1500.0,
            answer,
            failure,
        )
        self.future = _FakeInstrument(
            _NIFTY_FUTURE_ID,
            'nse_equity_index_futures',
            None,
            75,
            25000.0,
            answer,
            failure,
        )
        self.engine = _FakeEngine(reasons)
        self.order_book = trader_order_book.TraderOrderBook(
            tmp_path / 'trader_orders.db'
        )
        self.ledger = risk_ledger.RiskLedger(tmp_path / 'risk_ledger.db')
        event_bus = event_bus_module.EventBus()
        self.subscription = event_bus.subscribe()
        snapshot = account_snapshot.AccountSnapshot(
            total_balance=100000.0,
            margin_utilized=0.0,
            day_pnl=0.0,
            positions=positions,
        )
        self.services = order_tool.OrderServices(
            reader=_FakeReader(
                {
                    _INFY_ID: self.share,
                    _NIFTY_FUTURE_ID: self.future,
                }
            ),
            risk_engine=self.engine,
            order_book=self.order_book,
            snapshot_reader=_FakeSnapshotReader(snapshot),
            ledger=self.ledger,
            event_bus=event_bus,
            formatter=result_formatter.ResultFormatter(),
        )

    def order_events(self) -> list[dict[str, Any]]:
        """The payloads of the order events published so far.

        Returns:
            list[dict[str, Any]]: The payloads, oldest first.
        """
        payloads = []
        while not self.subscription._queue.empty():
            published = self.subscription._queue.get_nowait()
            if published.kind == event_module.EventKind.ORDER:
                payloads.append(published.payload)
        return payloads


def _limit_buy(
    instrument_id: str = _INFY_ID, quantity: int = 10
) -> order_arguments.OrderArguments:
    """A limit buy for the tests.

    Args:
        instrument_id (str): The instrument.
        quantity (int): How many units.

    Returns:
        order_arguments.OrderArguments: The order.
    """
    return order_arguments.OrderArguments(
        instrument_id=instrument_id,
        transaction_type='buy',
        quantity=quantity,
        product='mis',
        order_type='limit',
        price=1490.0,
        reason='test entry',
    )


class TestOrderArguments:
    """Tests for the price checks on order arguments."""

    def test_a_limit_order_needs_a_price(self) -> None:
        """A limit order without a price is refused before anything runs."""
        with pytest.raises(pydantic.ValidationError, match='needs a price'):
            order_arguments.OrderArguments(
                instrument_id=_INFY_ID,
                transaction_type='buy',
                quantity=1,
                product='mis',
                order_type='limit',
                reason='test',
            )

    def test_a_market_order_takes_no_price(self) -> None:
        """A market order with a price is refused."""
        with pytest.raises(pydantic.ValidationError, match='takes no price'):
            order_arguments.OrderArguments(
                instrument_id=_INFY_ID,
                transaction_type='buy',
                quantity=1,
                product='mis',
                order_type='market',
                price=10.0,
                reason='test',
            )

    def test_a_stop_market_order_needs_a_trigger(self) -> None:
        """An sl-m order without a trigger price is refused."""
        with pytest.raises(pydantic.ValidationError, match='trigger_price'):
            order_arguments.OrderArguments(
                instrument_id=_INFY_ID,
                transaction_type='sell',
                quantity=1,
                product='mis',
                order_type='sl-m',
                reason='test',
            )


class TestPlaceOrderTool:
    """Tests for place_order."""

    def test_dry_run_sends_a_tagged_dry_run(self, tmp_path: Path) -> None:
        """In dry_run mode the order goes to UBI as a dry run tagged with the trader.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)
        tool = place_order_tool.PlaceOrderTool(
            setup.services, 'main', 'dry_run'
        )

        result = asyncio.run(tool.run(_limit_buy()))

        assert not result.is_error
        method, sent = setup.share.requests[0]
        assert method == 'place_order'
        assert sent['dry_run'] is True
        assert sent['tag'] == 'main'
        assert 'dry run' in result.text

    def test_dry_run_order_is_recorded_under_a_made_up_id(
        self, tmp_path: Path
    ) -> None:
        """A dry run gets no id from UBI, so it is recorded under a dry- id.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)
        tool = place_order_tool.PlaceOrderTool(
            setup.services, 'main', 'dry_run'
        )

        asyncio.run(tool.run(_limit_buy()))

        records = setup.order_book.open_orders('main')
        assert len(records) == 1
        assert records[0].parent_id.startswith('dry-')
        assert records[0].dry_run is True

    def test_live_order_is_recorded_under_its_parent_id(
        self, tmp_path: Path
    ) -> None:
        """A live order is recorded under the parent_id UBI answered with.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(
            tmp_path,
            answer={
                'outcome': 'armed',
                'parent_id': 'parent-1',
                'order_id': None,
            },
        )
        tool = place_order_tool.PlaceOrderTool(setup.services, 'main', 'live')

        result = asyncio.run(tool.run(_limit_buy()))

        assert setup.share.requests[0][1]['dry_run'] is False
        assert 'parent_id: parent-1' in result.text
        record = setup.order_book.find('main', 'parent-1', None)
        assert record is not None
        assert record.dry_run is False

    def test_refused_order_sends_nothing(self, tmp_path: Path) -> None:
        """When the risk engine refuses, nothing reaches UBI and every reason is given.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(
            tmp_path,
            reasons=(
                'first reason',
                'second reason',
            ),
        )
        tool = place_order_tool.PlaceOrderTool(setup.services, 'main', 'live')

        result = asyncio.run(tool.run(_limit_buy()))

        assert result.is_error
        assert setup.share.requests == []
        assert '- first reason' in result.text
        assert '- second reason' in result.text
        assert setup.order_book.open_orders('main') == []

    def test_quantity_must_be_whole_lots(self, tmp_path: Path) -> None:
        """A future's quantity that is not a multiple of its lot is refused before the engine is asked.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)
        tool = place_order_tool.PlaceOrderTool(setup.services, 'main', 'live')

        result = asyncio.run(
            tool.run(_limit_buy(instrument_id=_NIFTY_FUTURE_ID, quantity=30))
        )

        assert result.is_error
        assert 'multiple of 75' in result.text
        assert setup.engine.requests == []

    def test_market_order_is_valued_at_the_last_price(
        self, tmp_path: Path
    ) -> None:
        """The risk engine values a market order at the last traded price.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)
        tool = place_order_tool.PlaceOrderTool(setup.services, 'main', 'live')
        arguments = order_arguments.OrderArguments(
            instrument_id=_INFY_ID,
            transaction_type='buy',
            quantity=5,
            product='cnc',
            order_type='market',
            reason='test',
        )

        asyncio.run(tool.run(arguments))

        assert setup.engine.requests[0].price == 1500.0
        assert setup.engine.requests[0].symbol == 'INFY'

    def test_future_uses_its_underlying_symbol(self, tmp_path: Path) -> None:
        """A future has no symbol of its own, so the engine sees its underlying's.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)
        tool = place_order_tool.PlaceOrderTool(setup.services, 'main', 'live')

        asyncio.run(
            tool.run(_limit_buy(instrument_id=_NIFTY_FUTURE_ID, quantity=75))
        )

        assert setup.engine.requests[0].symbol == 'NIFTY'

    def test_placement_is_published_with_the_reason(
        self, tmp_path: Path
    ) -> None:
        """An order event carries the model's reason, for the journal.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)
        tool = place_order_tool.PlaceOrderTool(
            setup.services, 'main', 'dry_run'
        )

        asyncio.run(tool.run(_limit_buy()))

        events = setup.order_events()
        assert events[0]['action'] == 'placed'
        assert events[0]['reason'] == 'test entry'
        assert events[0]['dry_run'] is True

    def test_unknown_outcome_warns_against_a_second_order(
        self, tmp_path: Path
    ) -> None:
        """When UBI times out, the model is told to check before retrying.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(
            tmp_path,
            failure=ubi_exceptions.OrderOutcomeUnknownError(
                'timed out', None, None
            ),
        )
        tool = place_order_tool.PlaceOrderTool(setup.services, 'main', 'live')

        result = asyncio.run(tool.run(_limit_buy()))

        assert result.is_error
        assert 'Check get_orders' in result.text

    def test_tag_keeps_only_letters_and_digits(self, tmp_path: Path) -> None:
        """UBI's tag allows only letters and digits, so the trader name is cleaned.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)
        tool = place_order_tool.PlaceOrderTool(
            setup.services, 'intraday-trader_1', 'dry_run'
        )

        asyncio.run(tool.run(_limit_buy()))

        assert setup.share.requests[0][1]['tag'] == 'intradaytrader1'


def _bracket(
    stop_price: float = 1470.0,
    stop_limit_price: float = 1468.0,
    target_price: float = 1530.0,
) -> place_bracket_order_tool.BracketOrderArguments:
    """A bracket buy at 1490 for the tests.

    Args:
        stop_price (float): The stop's trigger.
        stop_limit_price (float): The stop's limit.
        target_price (float): The target.

    Returns:
        place_bracket_order_tool.BracketOrderArguments: The bracket.
    """
    return place_bracket_order_tool.BracketOrderArguments(
        instrument_id=_INFY_ID,
        transaction_type='buy',
        quantity=10,
        product='mis',
        order_type='limit',
        price=1490.0,
        stop_price=stop_price,
        stop_limit_price=stop_limit_price,
        target_price=target_price,
        reason='test bracket',
    )


class TestPlaceBracketOrderTool:
    """Tests for place_bracket_order."""

    def test_bracket_is_sent_as_a_synthetic_bracket(
        self, tmp_path: Path
    ) -> None:
        """The stop and target travel in UBI's synthetic bracket object.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)
        tool = place_bracket_order_tool.PlaceBracketOrderTool(
            setup.services, 'main', 'dry_run'
        )

        result = asyncio.run(tool.run(_bracket()))

        assert not result.is_error
        sent = setup.share.requests[0][1]
        assert sent['synthetic']['type'] == 'bracket'
        assert sent['synthetic']['stop_price'] == 1470.0
        assert sent['synthetic']['target_price'] == 1530.0
        assert sent['tag'] == 'main'
        assert sent['dry_run'] is True

    def test_stop_above_a_buy_entry_is_refused(self, tmp_path: Path) -> None:
        """A buy's stop above its entry is caught before the risk engine is asked.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)
        tool = place_bracket_order_tool.PlaceBracketOrderTool(
            setup.services, 'main', 'dry_run'
        )

        result = asyncio.run(
            tool.run(_bracket(stop_price=1500.0, stop_limit_price=1499.0))
        )

        assert result.is_error
        assert 'must be below the entry price' in result.text
        assert setup.engine.requests == []

    def test_a_stop_needs_its_limit(self) -> None:
        """A stop without a stop_limit_price is refused by the arguments."""
        with pytest.raises(pydantic.ValidationError, match='stop_limit_price'):
            place_bracket_order_tool.BracketOrderArguments(
                instrument_id=_INFY_ID,
                transaction_type='buy',
                quantity=10,
                product='mis',
                order_type='limit',
                price=1490.0,
                stop_price=1470.0,
                reason='test',
            )


def _place_dry_run(setup: _Setup, trader: str = 'main') -> str:
    """Places a dry-run limit buy and returns its parent_id.

    Args:
        setup (_Setup): The services.
        trader (str): The trader placing it.

    Returns:
        str: The made-up parent_id.
    """
    tool = place_order_tool.PlaceOrderTool(setup.services, trader, 'dry_run')
    asyncio.run(tool.run(_limit_buy()))
    return setup.order_book.open_orders(trader)[0].parent_id


class TestModifyOrderTool:
    """Tests for modify_order."""

    def test_another_traders_order_cannot_be_changed(
        self, tmp_path: Path
    ) -> None:
        """A trader cannot change an order another trader placed.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)
        parent_id = _place_dry_run(setup, trader='scalper')
        tool = modify_order_tool.ModifyOrderTool(
            setup.services, 'main', 'dry_run'
        )

        result = asyncio.run(
            tool.run(
                modify_order_tool.ModifyOrderArguments(
                    parent_id=parent_id,
                    price=1480.0,
                    reason='test',
                )
            )
        )

        assert result.is_error
        assert 'placed no order with that id' in result.text

    def test_bigger_quantity_asks_the_engine_about_the_extra(
        self, tmp_path: Path
    ) -> None:
        """Growing an order from 10 to 25 asks the risk engine about 15 more.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)
        parent_id = _place_dry_run(setup)
        tool = modify_order_tool.ModifyOrderTool(
            setup.services, 'main', 'dry_run'
        )

        result = asyncio.run(
            tool.run(
                modify_order_tool.ModifyOrderArguments(
                    parent_id=parent_id,
                    quantity=25,
                    reason='adding',
                )
            )
        )

        assert not result.is_error
        assert setup.engine.requests[-1].quantity == 15
        record = setup.order_book.find('main', parent_id, None)
        assert record.quantity == 25

    def test_dry_run_order_change_is_only_recorded(
        self, tmp_path: Path
    ) -> None:
        """Changing a dry-run order sends nothing to UBI.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)
        parent_id = _place_dry_run(setup)
        tool = modify_order_tool.ModifyOrderTool(
            setup.services, 'main', 'dry_run'
        )
        requests_before = len(setup.share.requests)

        result = asyncio.run(
            tool.run(
                modify_order_tool.ModifyOrderArguments(
                    parent_id=parent_id,
                    price=1480.0,
                    reason='test',
                )
            )
        )

        assert 'only recorded' in result.text
        assert len(setup.share.requests) == requests_before
        assert setup.order_book.find('main', parent_id, None).price == 1480.0

    def test_live_order_change_goes_to_ubi(self, tmp_path: Path) -> None:
        """Changing a live order sends modify_order with its parent_id.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(
            tmp_path,
            answer={
                'outcome': 'armed',
                'parent_id': 'parent-1',
            },
        )
        place = place_order_tool.PlaceOrderTool(setup.services, 'main', 'live')
        asyncio.run(place.run(_limit_buy()))
        tool = modify_order_tool.ModifyOrderTool(setup.services, 'main', 'live')

        asyncio.run(
            tool.run(
                modify_order_tool.ModifyOrderArguments(
                    parent_id='parent-1',
                    price=1480.0,
                    reason='test',
                )
            )
        )

        method, sent = setup.share.requests[-1]
        assert method == 'modify_order'
        assert sent['parent_id'] == 'parent-1'
        assert sent['price'] == 1480.0
        assert sent['dry_run'] is False

    def test_naming_both_ids_is_refused(self) -> None:
        """An order is named by parent_id or order_id, not both."""
        with pytest.raises(pydantic.ValidationError, match='exactly one'):
            modify_order_tool.ModifyOrderArguments(
                parent_id='a',
                order_id='b',
                price=1.0,
                reason='test',
            )


class TestCancelOrderTool:
    """Tests for cancel_order."""

    def test_dry_run_order_is_cancelled_in_the_record(
        self, tmp_path: Path
    ) -> None:
        """Cancelling a dry-run order marks it cancelled, and a second cancel is refused.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)
        parent_id = _place_dry_run(setup)
        tool = cancel_order_tool.CancelOrderTool(
            setup.services, 'main', 'dry_run'
        )
        arguments = cancel_order_tool.CancelOrderArguments(
            parent_id=parent_id,
            reason='test',
        )

        first = asyncio.run(tool.run(arguments))
        second = asyncio.run(tool.run(arguments))

        assert not first.is_error
        assert setup.order_book.open_orders('main') == []
        assert second.is_error
        assert 'already cancelled' in second.text

    def test_live_order_is_cancelled_through_the_engine(
        self, tmp_path: Path
    ) -> None:
        """An order with a parent_id is cancelled with cancel_parent, even when named by order_id.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(
            tmp_path,
            answer={
                'outcome': 'accepted',
                'parent_id': 'parent-1',
                'order_id': 'broker-9',
            },
        )
        place = place_order_tool.PlaceOrderTool(setup.services, 'main', 'live')
        asyncio.run(place.run(_limit_buy()))
        tool = cancel_order_tool.CancelOrderTool(setup.services, 'main', 'live')

        asyncio.run(
            tool.run(
                cancel_order_tool.CancelOrderArguments(
                    order_id='broker-9',
                    reason='test',
                )
            )
        )

        method, sent = setup.share.requests[-1]
        assert method == 'cancel_parent'
        assert sent['parent_id'] == 'parent-1'
        assert sent['dry_run'] is False
        assert setup.order_book.open_orders('main') == []


class TestFlattenTraderTool:
    """Tests for flatten_trader."""

    def test_flatten_cancels_orders_and_closes_only_owned_positions(
        self, tmp_path: Path
    ) -> None:
        """The trader's open order is cancelled and its own position closed, while a position it does not own is left alone.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        positions = (
            account_snapshot.PositionRow(
                instrument_id=_INFY_ID,
                symbol='INFY',
                segment='nse_equities',
                product='intraday',
                quantity=10,
                last_price=1500.0,
            ),
            account_snapshot.PositionRow(
                instrument_id=_NIFTY_FUTURE_ID,
                symbol='NIFTY',
                segment='nse_equity_index_futures',
                product='carry',
                quantity=-75,
                last_price=25000.0,
            ),
        )
        setup = _Setup(tmp_path, positions=positions)
        _place_dry_run(setup)
        setup.ledger.claim(
            _INFY_ID,
            'main',
            datetime.datetime.now(datetime.UTC),
        )
        tool = flatten_trader_tool.FlattenTraderTool(
            setup.services, 'main', 'dry_run'
        )

        result = asyncio.run(
            tool.run(flatten_trader_tool.FlattenTraderArguments(reason='test'))
        )

        assert not result.is_error
        assert 'Cancelled dry-run order' in result.text
        method, sent = setup.share.requests[-1]
        assert method == 'place_order'
        assert sent['transaction_type'] == 'sell'
        assert sent['quantity_reference'] == {
            'kind': 'liquidate_position',
            'product': 'intraday',
        }
        assert sent['dry_run'] is True
        assert setup.future.requests == []
        assert setup.engine.requests[-1].transaction_type == 'sell'

    def test_flatten_with_nothing_to_do_says_so(self, tmp_path: Path) -> None:
        """A trader with no orders and no positions is told it was already flat.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)
        tool = flatten_trader_tool.FlattenTraderTool(
            setup.services, 'main', 'dry_run'
        )

        result = asyncio.run(
            tool.run(flatten_trader_tool.FlattenTraderArguments(reason='test'))
        )

        assert 'no open orders and no positions' in result.text
