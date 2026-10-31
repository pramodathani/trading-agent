"""Tests for the risk engine, with a fake account and a fake kill switch, and the real limits, ledger and rules."""

import asyncio
import dataclasses
import datetime
import zoneinfo
from pathlib import Path

import pytest
from tradingmachine.unified_broker_interface import exceptions as ubi_exceptions

from trading_agent.configuration import agent_configuration
from trading_agent.risk import account_snapshot
from trading_agent.risk import exchange_hours
from trading_agent.risk import margin_estimator
from trading_agent.risk import order_request
from trading_agent.risk import risk_engine
from trading_agent.risk import risk_ledger
from trading_agent.risk import trading_limits
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module

_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')
_MONDAY_MORNING = datetime.datetime(2026, 10, 19, 10, 30, tzinfo=_INDIA)
_SATURDAY_MORNING = datetime.datetime(2026, 10, 17, 10, 30, tzinfo=_INDIA)
_LIMITS = """
[account]
trading_enabled = true
capital_percent = 100
daily_loss_limit_percent = 15
weekly_loss_limit_percent = 35
maximum_order_value_percent = 25
trading_window = "exchange_hours"
allow_option_writing = false

[traders.main]
allowed_products = []
allowed_instruments = []
"""


class _FakeSnapshotReader:
    """Returns a fixed account snapshot, or raises.

    Attributes:
        snapshot: The snapshot to return.
        failure: An exception to raise instead, or None.
    """

    def __init__(self, snapshot: account_snapshot.AccountSnapshot):
        """Creates the reader.

        Args:
            snapshot (account_snapshot.AccountSnapshot): The snapshot to return.
        """
        self.snapshot = snapshot
        self.failure = None

    async def read(self) -> account_snapshot.AccountSnapshot:
        """Returns the snapshot.

        Returns:
            account_snapshot.AccountSnapshot: The snapshot.

        Raises:
            Exception: The failure, when one is set.
        """
        if self.failure is not None:
            raise self.failure
        return self.snapshot


class _FakeKillSwitch:
    """Records halts in the real ledger without calling UBI, like the real switch.

    Attributes:
        triggers: The reasons it was fired with.
    """

    def __init__(self, ledger: risk_ledger.RiskLedger):
        """Creates the switch.

        Args:
            ledger (risk_ledger.RiskLedger): Where the halt is recorded.
        """
        self._ledger = ledger
        self.triggers = []

    async def trigger(
        self,
        reason: str,
        until_date: datetime.date,
        now: datetime.datetime,
    ) -> dict:
        """Records the halt once, as the real switch does.

        Args:
            reason (str): Why.
            until_date (datetime.date): The first day trading is allowed again.
            now (datetime.datetime): The current time.

        Returns:
            dict: A stand-in for UBI's answer.
        """
        if (
            self._ledger.active_halt(risk_ledger.ACCOUNT_SCOPE, now.date())
            is not None
        ):
            return {
                'already_halted': True,
            }
        self._ledger.halt(risk_ledger.ACCOUNT_SCOPE, reason, until_date, now)
        self.triggers.append(reason)
        return {
            'dry_run': True,
        }


def _snapshot(
    day_pnl: float = 0.0,
    positions: tuple = (),
    held_quantities: dict | None = None,
    held_symbols: frozenset = frozenset(),
    margin_utilized: float = 0.0,
) -> account_snapshot.AccountSnapshot:
    """Builds an account with a total balance of 150,000.

    Args:
        day_pnl (float): Today's profit or loss.
        positions (tuple): The open positions.
        held_quantities (dict | None): Holdings by instrument id.
        held_symbols (frozenset): The symbols of the holdings.
        margin_utilized (float): Margin already in use.

    Returns:
        account_snapshot.AccountSnapshot: The account.
    """
    return account_snapshot.AccountSnapshot(
        total_balance=150000.0,
        margin_utilized=margin_utilized,
        day_pnl=day_pnl,
        positions=positions,
        held_quantities=held_quantities or {},
        held_symbols=held_symbols,
    )


def _order(**changes) -> order_request.OrderRequest:
    """Builds an order: buy 10 INFY on nse in cnc at 1,500, unless changed.

    Args:
        **changes: Fields to change.

    Returns:
        order_request.OrderRequest: The order.
    """
    fields = {
        'trader': 'main',
        'instrument_id': 'infy',
        'exchange': 'nse',
        'segment': 'nse_equities',
        'symbol': 'INFY',
        'transaction_type': 'buy',
        'quantity': 10,
        'product': 'cnc',
        'price': 1500.0,
    }
    fields.update(changes)
    return order_request.OrderRequest(**fields)


class _Setup:
    """A risk engine with its fakes, in a temporary workspace.

    Attributes:
        rules_file: The TradingRules.md the engine reads.
        snapshots: The fake account.
        ledger: The real ledger.
        kill_switch: The fake kill switch.
        decisions: The risk_decision events published.
        now: The clock's current time.
    """

    def __init__(self, tmp_path: Path, limits: str = _LIMITS):
        """Builds the engine.

        Args:
            tmp_path (Path): A temporary folder from pytest.
            limits (str): The text of the limits block.
        """
        self.rules_file = tmp_path / 'TradingRules.md'
        self.write_limits(limits)
        self.snapshots = _FakeSnapshotReader(_snapshot())
        self.ledger = risk_ledger.RiskLedger(tmp_path / 'risk_ledger.db')
        self.kill_switch = _FakeKillSwitch(self.ledger)
        self.now = _MONDAY_MORNING
        self._event_bus = event_bus_module.EventBus()
        self._subscription = self._event_bus.subscribe()
        services = risk_engine.RiskServices(
            limits_reader=trading_limits.TradingLimitsReader(self.rules_file),
            snapshot_reader=self.snapshots,
            ledger=self.ledger,
            kill_switch=self.kill_switch,
            margin_estimator=margin_estimator.MarginEstimator(
                agent_configuration.MarginRatesConfiguration()
            ),
            exchange_hours=exchange_hours.ExchangeHours(),
        )
        self.engine = risk_engine.RiskEngine(
            services,
            self._event_bus,
            datetime.timedelta(minutes=30),
            clock=lambda: self.now,
        )

    def write_limits(self, limits: str) -> None:
        """Writes TradingRules.md with a limits block.

        Args:
            limits (str): The block's text.
        """
        self.rules_file.write_text(
            f'# Rules\n\n```toml limits\n{limits}\n```\n', encoding='utf-8'
        )

    def evaluate(
        self, order: order_request.OrderRequest
    ) -> risk_engine.RiskDecision:
        """Runs the engine on one order.

        Args:
            order (order_request.OrderRequest): The order.

        Returns:
            risk_engine.RiskDecision: The decision.
        """
        return asyncio.run(self.engine.evaluate(order))

    def reasons(self, order: order_request.OrderRequest) -> str:
        """Runs the engine and joins the refusal reasons.

        Args:
            order (order_request.OrderRequest): The order.

        Returns:
            str: The reasons, one per line, or an empty string when approved.
        """
        return '\n'.join(self.evaluate(order).reasons)


class TestApprovalAndHours:
    """Tests for ordinary approvals and exchange hours."""

    def test_ordinary_buy_in_market_hours_is_approved_and_claimed(
        self, tmp_path: Path
    ) -> None:
        """A small delivery buy on a Monday morning passes, and the trader now owns the instrument.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)

        decision = setup.evaluate(_order())

        assert decision.approved
        assert decision.estimated_margin == 15000.0
        assert setup.ledger.owner('infy') == 'main'

    def test_weekend_is_refused(self, tmp_path: Path) -> None:
        """No order passes on a Saturday.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)
        setup.now = _SATURDAY_MORNING

        assert 'weekend' in setup.reasons(_order())

    def test_mcx_evening_follows_us_daylight_saving(self) -> None:
        """At 23:40 India time MCX is closed in July (US daylight saving) and open in January."""
        hours = exchange_hours.ExchangeHours()
        july = datetime.datetime(2026, 7, 15, 23, 40, tzinfo=_INDIA)
        january = datetime.datetime(2026, 1, 14, 23, 40, tzinfo=_INDIA)

        assert not hours.is_open(
            'mcx', 'mcx_commodity_futures', july, 'exchange_hours'
        )[0]
        assert hours.is_open(
            'mcx', 'mcx_commodity_futures', january, 'exchange_hours'
        )[0]

    def test_nse_closes_at_half_past_three(self) -> None:
        """NSE equities are open at 15:29 and closed at 15:30."""
        hours = exchange_hours.ExchangeHours()
        at_15_29 = datetime.datetime(2026, 10, 19, 15, 29, tzinfo=_INDIA)
        at_15_30 = datetime.datetime(2026, 10, 19, 15, 30, tzinfo=_INDIA)

        assert hours.is_open('nse', 'nse_equities', at_15_29, 'exchange_hours')[
            0
        ]
        assert not hours.is_open(
            'nse', 'nse_equities', at_15_30, 'exchange_hours'
        )[0]

    def test_decision_is_published(self, tmp_path: Path) -> None:
        """Every decision is published as a risk_decision event with the order and reasons.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)
        setup.now = _SATURDAY_MORNING

        setup.evaluate(_order())

        published = setup._subscription._queue.get_nowait()
        assert published.kind == event_module.EventKind.RISK_DECISION
        assert published.payload['approved'] is False
        assert (
            published.payload['order']
            == 'buy 10 INFY (nse_equities, cnc) at 1500'
        )


class TestLimits:
    """Tests for the limits in TradingRules.md."""

    def test_margin_above_the_per_order_cap_is_refused(
        self, tmp_path: Path
    ) -> None:
        """One NIFTY futures lot blocks about 167,000 of margin, above 25% of 150,000.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)
        future = _order(
            instrument_id='nifty-fut',
            segment='nse_equity_index_futures',
            symbol='NIFTY',
            quantity=75,
            product='nrml',
            price=23000.0,
        )

        reasons = setup.reasons(future)

        assert 'per-order cap' in reasons
        assert '37,500.00' in reasons

    def test_intraday_margin_is_a_fifth_of_the_value(
        self, tmp_path: Path
    ) -> None:
        """An intraday order of 150,000 value blocks 30,000, which fits the 37,500 cap.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)

        decision = setup.evaluate(_order(quantity=100, product='mis'))

        assert decision.approved
        assert decision.estimated_margin == pytest.approx(30000.0)

    def test_capital_already_in_use_is_counted(self, tmp_path: Path) -> None:
        """With 140,000 of margin in use, a 15,000 order exceeds the free capital.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)
        setup.snapshots.snapshot = _snapshot(margin_utilized=140000.0)

        assert 'still free' in setup.reasons(_order())

    def test_trading_disabled_refuses_new_positions(
        self, tmp_path: Path
    ) -> None:
        """With trading_enabled false nothing new may be opened.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(
            tmp_path,
            _LIMITS.replace(
                'trading_enabled = true', 'trading_enabled = false'
            ),
        )

        assert 'trading_enabled is false' in setup.reasons(_order())

    def test_unreadable_rules_refuse_opening(self, tmp_path: Path) -> None:
        """A missing limits block refuses every order that opens a position.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)
        setup.rules_file.write_text(
            '# Rules without a limits block\n', encoding='utf-8'
        )

        assert 'cannot be read' in setup.reasons(_order())

    def test_unreadable_account_refuses_everything(
        self, tmp_path: Path
    ) -> None:
        """When UBI cannot report the account, no order can be checked, so none passes.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)
        setup.snapshots.failure = ubi_exceptions.ServiceUnavailableError(
            'down', 503, None
        )

        assert 'cannot be read from UBI' in setup.reasons(_order())

    def test_trader_product_list_is_enforced(self, tmp_path: Path) -> None:
        """A trader limited to mis cannot place a cnc order.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(
            tmp_path,
            _LIMITS.replace(
                'allowed_products = []', 'allowed_products = ["mis"]'
            ),
        )

        assert 'Product cnc is not allowed' in setup.reasons(_order())

    def test_open_positions_cap(self, tmp_path: Path) -> None:
        """With a cap of one and one instrument held, a second instrument is refused.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(
            tmp_path,
            _LIMITS.replace(
                'allow_option_writing = false',
                'allow_option_writing = false\nmaximum_open_positions = 1',
            ),
        )
        setup.ledger.claim('tcs', 'main', setup.now)
        setup.snapshots.snapshot = _snapshot(
            positions=(
                account_snapshot.PositionRow(
                    'tcs', 'TCS', 'nse_equities', 'delivery', 5, 3000.0
                ),
            ),
        )

        assert 'maximum_open_positions' in setup.reasons(_order())

    def test_orders_per_minute_cap(self, tmp_path: Path) -> None:
        """With a cap of two per minute, the third order within a minute is refused.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(
            tmp_path,
            _LIMITS.replace(
                'allowed_instruments = []',
                'allowed_instruments = []\nmaximum_orders_per_minute = 2',
            ),
        )

        first = setup.evaluate(_order(quantity=1))
        second = setup.evaluate(_order(quantity=1))
        third = setup.evaluate(_order(quantity=1))

        assert first.approved and second.approved
        assert 'in the last minute' in '\n'.join(third.reasons)


class TestOptions:
    """Tests for the no-option-writing rule."""

    def _option(self, **changes) -> order_request.OrderRequest:
        """Builds an option order: buy one lot of a NIFTY call at a premium of 100.

        Args:
            **changes: Fields to change.

        Returns:
            order_request.OrderRequest: The order.
        """
        fields = {
            'instrument_id': 'nifty-23000-ce',
            'segment': 'nse_equity_index_options',
            'symbol': 'NIFTY',
            'quantity': 75,
            'product': 'nrml',
            'price': 100.0,
        }
        fields.update(changes)
        return _order(**fields)

    def test_buying_an_option_costs_its_premium(self, tmp_path: Path) -> None:
        """An option buy is approved and its margin is the premium paid.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        decision = _Setup(tmp_path).evaluate(self._option())

        assert decision.approved
        assert decision.estimated_margin == 7500.0

    def test_selling_an_option_to_open_is_refused(self, tmp_path: Path) -> None:
        """Selling an option the trader does not hold is option writing, which is refused.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)

        assert 'option writing' in setup.reasons(
            self._option(transaction_type='sell')
        )

    def test_selling_an_option_the_trader_holds_is_allowed(
        self, tmp_path: Path
    ) -> None:
        """Selling back an option the trader bought only closes a position, so it passes.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)
        setup.ledger.claim('nifty-23000-ce', 'main', setup.now)
        setup.snapshots.snapshot = _snapshot(
            positions=(
                account_snapshot.PositionRow(
                    'nifty-23000-ce',
                    'NIFTY',
                    'nse_equity_index_options',
                    'carry',
                    75,
                    100.0,
                ),
            ),
        )

        assert setup.evaluate(self._option(transaction_type='sell')).approved

    def test_selling_more_than_held_is_writing(self, tmp_path: Path) -> None:
        """Selling 150 when 75 are held would leave a short position, so it is refused.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)
        setup.ledger.claim('nifty-23000-ce', 'main', setup.now)
        setup.snapshots.snapshot = _snapshot(
            positions=(
                account_snapshot.PositionRow(
                    'nifty-23000-ce',
                    'NIFTY',
                    'nse_equity_index_options',
                    'carry',
                    75,
                    100.0,
                ),
            ),
        )

        assert 'option writing' in setup.reasons(
            self._option(transaction_type='sell', quantity=150)
        )


class TestOwnership:
    """Tests for one trader per instrument and for the user's own holdings."""

    def test_instrument_owned_by_another_trader_is_refused(
        self, tmp_path: Path
    ) -> None:
        """When the scalper trader owns INFY, the main trader cannot trade it.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)
        setup.ledger.claim('infy', 'scalper', setup.now)

        assert 'belongs to the scalper trader' in setup.reasons(_order())

    def test_users_own_holding_is_protected_by_id(self, tmp_path: Path) -> None:
        """A trader cannot sell, or add to, shares the user holds outside the agent.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)
        setup.snapshots.snapshot = _snapshot(held_quantities={'infy': 20})

        assert 'outside the agent' in setup.reasons(
            _order(transaction_type='sell')
        )

    def test_users_holding_without_an_id_is_protected_by_symbol(
        self, tmp_path: Path
    ) -> None:
        """A holding UBI gives no instrument id is still protected, by its symbol.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)
        setup.snapshots.snapshot = _snapshot(held_symbols=frozenset({'KWIL'}))

        reasons = setup.reasons(
            _order(instrument_id='kwil', symbol='KWIL', transaction_type='sell')
        )

        assert 'outside the agent' in reasons

    def test_claim_lapses_after_the_grace_period_without_a_position(
        self, tmp_path: Path
    ) -> None:
        """A claim with no position is released after 30 minutes, so another trader may then trade.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)
        setup.ledger.claim(
            'infy', 'scalper', setup.now - datetime.timedelta(minutes=31)
        )

        assert setup.evaluate(_order()).approved
        assert setup.ledger.owner('infy') == 'main'


class TestLossLimits:
    """Tests for the daily and weekly loss limits and the kill switch."""

    def test_daily_loss_fires_the_kill_switch_once(
        self, tmp_path: Path
    ) -> None:
        """A loss of 23,000 on 150,000 passes 15%, fires the switch once, and halts new positions.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)
        setup.snapshots.snapshot = _snapshot(day_pnl=-23000.0)

        first = setup.evaluate(_order())
        second = setup.evaluate(_order())

        assert len(setup.kill_switch.triggers) == 1
        assert 'Daily loss limit reached' in setup.kill_switch.triggers[0]
        assert 'halted for the account' in '\n'.join(first.reasons)
        assert not second.approved

    def test_loss_below_the_limit_does_nothing(self, tmp_path: Path) -> None:
        """A loss of 22,000, under 15% of 150,000 (22,500), does not fire the switch.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)
        setup.snapshots.snapshot = _snapshot(day_pnl=-22000.0)

        assert setup.evaluate(_order()).approved
        assert setup.kill_switch.triggers == []

    def test_closing_own_position_is_allowed_while_halted(
        self, tmp_path: Path
    ) -> None:
        """After the switch fires, the trader may still sell what it bought.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)
        setup.ledger.claim('infy', 'main', setup.now)
        setup.snapshots.snapshot = _snapshot(
            day_pnl=-30000.0,
            positions=(
                account_snapshot.PositionRow(
                    'infy', 'INFY', 'nse_equities', 'delivery', 10, 1400.0
                ),
            ),
        )

        decision = setup.evaluate(_order(transaction_type='sell'))

        assert setup.kill_switch.triggers
        assert decision.approved

    def test_weekly_loss_adds_up_the_days(self, tmp_path: Path) -> None:
        """Losses of 20,000 on Monday and 20,000 on Tuesday pass 35% of 150,000 (52,500) only with Wednesday's 15,000.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)
        setup.ledger.record_day_pnl(datetime.date(2026, 10, 19), -20000.0)
        setup.ledger.record_day_pnl(datetime.date(2026, 10, 20), -20000.0)
        setup.now = datetime.datetime(2026, 10, 21, 10, 30, tzinfo=_INDIA)
        setup.snapshots.snapshot = _snapshot(day_pnl=-15000.0)

        setup.evaluate(_order())

        assert len(setup.kill_switch.triggers) == 1
        assert 'Weekly loss limit reached' in setup.kill_switch.triggers[0]
        halt = setup.ledger.active_halt(
            risk_ledger.ACCOUNT_SCOPE, datetime.date(2026, 10, 25)
        )
        assert halt is not None
        assert (
            setup.ledger.active_halt(
                risk_ledger.ACCOUNT_SCOPE, datetime.date(2026, 10, 26)
            )
            is None
        )


class TestLimitsReader:
    """Tests for reading the limits block."""

    def test_bad_value_is_reported(self, tmp_path: Path) -> None:
        """A percentage above 100 makes the block invalid.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        rules_file = tmp_path / 'TradingRules.md'
        rules_file.write_text(
            '```toml limits\n[account]\ncapital_percent = 150\n```\n',
            encoding='utf-8',
        )

        with pytest.raises(trading_limits.LimitsError, match='not valid'):
            trading_limits.TradingLimitsReader(rules_file).read()

    def test_trader_without_an_entry_gets_no_extra_limits(
        self, tmp_path: Path
    ) -> None:
        """A trader missing from [traders] has empty lists and no caps.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        rules_file = tmp_path / 'TradingRules.md'
        rules_file.write_text(
            '```toml limits\n[account]\ntrading_enabled = true\n```\n',
            encoding='utf-8',
        )

        trader = (
            trading_limits.TradingLimitsReader(rules_file)
            .read()
            .trader('scalper')
        )

        assert trader.allowed_products == []
        assert trader.maximum_orders_per_minute is None


class TestAccountCheck:
    """The market watcher's account check fires the kill switch without an order."""

    def test_loss_limit_fires_without_an_order(self, tmp_path: Path) -> None:
        """A 23,000 loss on 150,000 fires the switch once from check_account alone.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)
        setup.snapshots.snapshot = _snapshot(day_pnl=-23000.0)

        snapshot = asyncio.run(setup.engine.check_account())
        asyncio.run(setup.engine.check_account())

        assert snapshot.day_pnl == -23000.0
        assert len(setup.kill_switch.triggers) == 1
        assert 'Daily loss limit reached' in setup.kill_switch.triggers[0]

    def test_small_loss_does_nothing(self, tmp_path: Path) -> None:
        """A 1,000 loss leaves the switch alone.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path)
        setup.snapshots.snapshot = _snapshot(day_pnl=-1000.0)

        asyncio.run(setup.engine.check_account())

        assert setup.kill_switch.triggers == []


_TRADER_LIMITS = (
    _LIMITS
    + """
[traders.intraday]
allowed_products = ["mis"]

[traders.scalper]
allowed_products = ["mis"]
daily_loss_limit_percent = 2

[traders.positional]
allowed_products = ["cnc", "nrml"]
"""
)


class TestTraders:
    """Several traders share one account and one risk engine."""

    def test_two_traders_cannot_trade_the_same_stock(
        self, tmp_path: Path
    ) -> None:
        """Intraday gets INFY first; the scalper is then refused it; positional may not use mis.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path, _TRADER_LIMITS)

        intraday = setup.evaluate(_order(trader='intraday', product='mis'))
        scalper = setup.evaluate(_order(trader='scalper', product='mis'))
        positional = setup.evaluate(
            _order(
                trader='positional',
                product='mis',
                instrument_id='tcs',
                symbol='TCS',
            )
        )

        assert intraday.approved
        assert not scalper.approved
        assert 'intraday' in '\n'.join(scalper.reasons)
        assert not positional.approved
        assert 'mis' in '\n'.join(positional.reasons)

    def test_trader_loss_limit_stops_only_that_trader(
        self, tmp_path: Path
    ) -> None:
        """A 5,000 loss on a stock the scalper held, closed and gave up, halts the scalper alone.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        setup = _Setup(tmp_path, _TRADER_LIMITS)
        setup.ledger.claim('idea', 'scalper', setup.now)
        setup.ledger.release_unheld(set(), setup.now, datetime.timedelta(0))
        assert setup.ledger.owner('idea') is None
        setup.snapshots.snapshot = dataclasses.replace(
            _snapshot(day_pnl=-5000.0),
            day_pnl_by_instrument={
                'idea': -5000.0,
            },
        )

        intraday = setup.evaluate(
            _order(
                trader='intraday',
                product='mis',
                instrument_id='tcs',
                symbol='TCS',
            )
        )
        scalper = setup.evaluate(
            _order(
                trader='scalper',
                product='mis',
                instrument_id='sbin',
                symbol='SBIN',
            )
        )

        assert setup.engine.trader_day_pnl(setup.snapshots.snapshot) == {
            'scalper': -5000.0,
        }
        assert intraday.approved
        assert not scalper.approved
        assert "scalper trader's daily loss limit is reached" in '\n'.join(
            scalper.reasons
        )
        assert setup.kill_switch.triggers == []
