"""The risk engine: plain code that every order must pass before it reaches a broker.

No model can change it, talk to it or skip it. Before each order it reads the limits from TradingRules.md and the account from UBI, checks the loss limits and fires the kill switch when one is reached, and then checks the order against every rule, collecting every reason it fails so the model can fix the order in one step.

Two principles shape it. When the limits or the account cannot be read, the answer is no. And an order that only reduces or closes a trader's own position is never blocked by a limit or a halt, because getting out must always be possible.

Typical usage example:

  decision = await engine.evaluate(order_request)
  if decision.approved:
      ...
"""

import dataclasses
import datetime
import logging
import zoneinfo
from collections.abc import Callable

from tradingmachine.unified_broker_interface import exceptions as ubi_exceptions

from trading_agent.risk import account_snapshot as account_snapshot_module
from trading_agent.risk import exchange_hours as exchange_hours_module
from trading_agent.risk import kill_switch as kill_switch_module
from trading_agent.risk import margin_estimator as margin_estimator_module
from trading_agent.risk import order_request as order_request_module
from trading_agent.risk import risk_ledger as risk_ledger_module
from trading_agent.risk import trading_limits as trading_limits_module
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module

_LOGGER = logging.getLogger(__name__)
_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')
_ONE_MINUTE = datetime.timedelta(minutes=1)
_CASH_SEGMENT_WORD = 'equities'
_POSITION_PRODUCTS = {
    'intraday': 'mis',
    'delivery': 'cnc',
    'carry': 'nrml',
}


@dataclasses.dataclass(frozen=True)
class RiskDecision:
    """The engine's answer for one order.

    Attributes:
        approved: Whether the order may be sent.
        reasons: Why it was refused; empty when approved.
        estimated_margin: The margin the order is estimated to block, in rupees.
    """

    approved: bool
    reasons: tuple[str, ...]
    estimated_margin: float


@dataclasses.dataclass(frozen=True)
class RiskServices:
    """The parts the engine reads from and writes to.

    Attributes:
        limits_reader: Reads the limits from TradingRules.md.
        snapshot_reader: Reads the account from UBI.
        ledger: The engine's memory.
        kill_switch: Halts and flattens the account.
        margin_estimator: Estimates an order's margin.
        exchange_hours: Says whether an exchange is open.
    """

    limits_reader: trading_limits_module.TradingLimitsReader
    snapshot_reader: account_snapshot_module.AccountSnapshotReader
    ledger: risk_ledger_module.RiskLedger
    kill_switch: kill_switch_module.KillSwitch
    margin_estimator: margin_estimator_module.MarginEstimator
    exchange_hours: exchange_hours_module.ExchangeHours


class RiskEngine:
    """Checks every order against the limits and the account."""

    def __init__(
        self,
        services: RiskServices,
        event_bus: event_bus_module.EventBus,
        ownership_grace: datetime.timedelta,
        clock: Callable[[], datetime.datetime] | None = None,
    ):
        """Creates the engine.

        Args:
            services (RiskServices): What the engine reads and writes.
            event_bus (event_bus_module.EventBus): Where every decision is published.
            ownership_grace (datetime.timedelta): How long a trader keeps a claim on an instrument it does not hold yet.
            clock (Callable[[], datetime.datetime] | None): The source of the current time, replaceable in tests; None for the real clock.
        """
        self._services = services
        self._event_bus = event_bus
        self._ownership_grace = ownership_grace
        if clock is None:
            clock = self._real_now
        self._clock = clock

    async def evaluate(
        self,
        order: order_request_module.OrderRequest,
    ) -> RiskDecision:
        """Decides whether one order may be sent, and records an approval.

        Args:
            order (order_request_module.OrderRequest): The order.

        Returns:
            RiskDecision: The decision, with every reason when refused.
        """
        now = self._clock().astimezone(_INDIA)
        reasons = []
        limits_error = None
        try:
            limits = self._services.limits_reader.read()
        except trading_limits_module.LimitsError as error:
            limits = None
            limits_error = f'The trading rules cannot be read, so nothing new can be opened: {error}.'
        try:
            snapshot = await self._services.snapshot_reader.read()
        except ubi_exceptions.UnifiedBrokerInterfaceError as error:
            return self._finish(
                order,
                [
                    f'The account cannot be read from UBI right now ({type(error).__name__}), so no order can be checked.',
                ],
                0.0,
            )
        ledger = self._services.ledger
        ledger.record_day_pnl(now.date(), snapshot.day_pnl)
        ledger.release_unheld(
            snapshot.held_instrument_ids(), now, self._ownership_grace
        )
        if limits is not None:
            await self._check_loss_limits(limits.account, snapshot, now)
            self._check_trader_loss_limits(limits, snapshot, now)
        margin = self._services.margin_estimator.margin(order)
        reducing = self._reduces_own_position(order, snapshot)
        reasons.extend(self._market_reasons(order, limits, now))
        reasons.extend(self._ownership_reasons(order, snapshot))
        if not reducing and limits_error is not None:
            reasons.append(limits_error)
        if not reducing and limits is not None:
            reasons.extend(
                self._opening_reasons(order, limits, snapshot, margin, now)
            )
        if not reasons:
            claimed_at = self._claim_time(order, limits, now)
            ledger.claim(order.instrument_id, order.trader, claimed_at)
            ledger.record_approval(order.trader, now)
        return self._finish(order, reasons, margin)

    def _claim_time(
        self,
        order: order_request_module.OrderRequest,
        limits: trading_limits_module.TradingLimits | None,
        now: datetime.datetime,
    ) -> datetime.datetime:
        """The time an approved order's claim on its instrument is dated from.

        Args:
            order (order_request_module.OrderRequest): The approved order.
            limits (trading_limits_module.TradingLimits | None): The limits, or None when they cannot be read.
            now (datetime.datetime): The current time.

        Returns:
            datetime.datetime: The current time, or for an after-market order the time the exchange next opens, when the order can first fill.
        """
        if not order.after_market:
            return now
        return self._services.exchange_hours.next_open(
            order.exchange,
            order.segment,
            now,
            self._trading_window(limits),
        )

    def _trading_window(
        self,
        limits: trading_limits_module.TradingLimits | None,
    ) -> str:
        """The trading window the limits set.

        Args:
            limits (trading_limits_module.TradingLimits | None): The limits, or None when they cannot be read.

        Returns:
            str: "exchange_hours", or a fixed "HH:MM-HH:MM" window from TradingRules.md.
        """
        if limits is None:
            return 'exchange_hours'
        return limits.account.trading_window

    async def check_account(
        self,
    ) -> account_snapshot_module.AccountSnapshot | None:
        """Reads the account and fires the kill switch at a loss limit, without an order.

        The market watcher calls this every cycle, because a losing position can reach the daily or weekly loss limit while no trader is placing orders.

        Returns:
            account_snapshot_module.AccountSnapshot | None: The account now, or None when UBI cannot be read.
        """
        now = self._clock().astimezone(_INDIA)
        try:
            snapshot = await self._services.snapshot_reader.read()
        except ubi_exceptions.UnifiedBrokerInterfaceError:
            _LOGGER.warning(
                'The account could not be read for the loss-limit check'
            )
            return None
        self._services.ledger.record_day_pnl(now.date(), snapshot.day_pnl)
        try:
            limits = self._services.limits_reader.read()
        except trading_limits_module.LimitsError:
            return snapshot
        await self._check_loss_limits(limits.account, snapshot, now)
        self._check_trader_loss_limits(limits, snapshot, now)
        return snapshot

    def trader_day_pnl(
        self,
        snapshot: account_snapshot_module.AccountSnapshot,
    ) -> dict[str, float]:
        """Today's profit or loss of each trader, from the instruments it owned today.

        An instrument counts for the trader that last claimed it today, even after the position was closed and the claim released, so a loss taken on a closed trade still counts against the trader that took it. Positions no trader claimed, such as the user's own, count for no trader.

        Args:
            snapshot (account_snapshot_module.AccountSnapshot): The account now.

        Returns:
            dict[str, float]: Each trader's profit or loss, keyed by trader name; traders with nothing today are absent.
        """
        today = self._clock().astimezone(_INDIA).date()
        owners = self._services.ledger.day_owners(today)
        pnl = {}
        for instrument_id, amount in snapshot.day_pnl_by_instrument.items():
            trader = owners.get(instrument_id)
            if trader is None:
                continue
            pnl[trader] = pnl.get(trader, 0.0) + amount
        return pnl

    def _check_trader_loss_limits(
        self,
        limits: trading_limits_module.TradingLimits,
        snapshot: account_snapshot_module.AccountSnapshot,
        now: datetime.datetime,
    ) -> None:
        """Halts each trader whose own daily loss limit is reached, leaving the other traders trading.

        A halted trader can still reduce and close its own positions, as with every halt.

        Args:
            limits (trading_limits_module.TradingLimits): The limits.
            snapshot (account_snapshot_module.AccountSnapshot): The account now.
            now (datetime.datetime): The current time, in India time.
        """
        trader_pnl = self.trader_day_pnl(snapshot)
        for trader, trader_limits in limits.traders.items():
            percent = trader_limits.daily_loss_limit_percent
            if percent is None:
                continue
            limit = percent / 100 * snapshot.total_balance
            pnl = trader_pnl.get(trader, 0.0)
            if pnl >= 0 or pnl > -limit:
                continue
            if (
                self._services.ledger.active_halt(trader, now.date())
                is not None
            ):
                continue
            reason = f"The {trader} trader's daily loss limit is reached: its profit and loss today is {pnl:,.2f}, and its limit is {percent:g}% of {snapshot.total_balance:,.2f} = {limit:,.2f}. The other traders keep trading."
            self._services.ledger.halt(
                trader,
                reason,
                now.date() + datetime.timedelta(days=1),
                now,
            )
            self._event_bus.publish(
                event_module.Event.now(
                    event_module.EventKind.TRADER_HALT,
                    trader,
                    {
                        'reason': reason,
                        'trader_pnl': pnl,
                        'limit': limit,
                    },
                )
            )

    async def _check_loss_limits(
        self,
        limits: trading_limits_module.AccountLimits,
        snapshot: account_snapshot_module.AccountSnapshot,
        now: datetime.datetime,
    ) -> None:
        """Fires the kill switch when today's or this week's loss reaches its limit.

        Args:
            limits (trading_limits_module.AccountLimits): The account limits.
            snapshot (account_snapshot_module.AccountSnapshot): The account now.
            now (datetime.datetime): The current time, in India time.
        """
        daily_limit = (
            limits.daily_loss_limit_percent / 100 * snapshot.total_balance
        )
        if snapshot.day_pnl < 0 and snapshot.day_pnl <= -daily_limit:
            await self._services.kill_switch.trigger(
                f"Daily loss limit reached: today's profit and loss is {snapshot.day_pnl:,.2f}, and the limit is {limits.daily_loss_limit_percent:g}% of {snapshot.total_balance:,.2f} = {daily_limit:,.2f}.",
                now.date() + datetime.timedelta(days=1),
                now,
            )
            return
        week_pnl = self._services.ledger.week_pnl(now.date())
        weekly_limit = (
            limits.weekly_loss_limit_percent / 100 * snapshot.total_balance
        )
        if week_pnl < 0 and week_pnl <= -weekly_limit:
            next_monday = now.date() + datetime.timedelta(
                days=7 - now.weekday()
            )
            await self._services.kill_switch.trigger(
                f"Weekly loss limit reached: this week's profit and loss is {week_pnl:,.2f}, and the limit is {limits.weekly_loss_limit_percent:g}% of {snapshot.total_balance:,.2f} = {weekly_limit:,.2f}.",
                next_monday,
                now,
            )

    def _reduces_own_position(
        self,
        order: order_request_module.OrderRequest,
        snapshot: account_snapshot_module.AccountSnapshot,
    ) -> bool:
        """Whether an order only reduces or closes a position the trader itself opened.

        Args:
            order (order_request_module.OrderRequest): The order.
            snapshot (account_snapshot_module.AccountSnapshot): The account now.

        Returns:
            bool: True when the trader owns the instrument, the order is on the other side of the position, and it is no larger than the position.
        """
        if self._services.ledger.owner(order.instrument_id) != order.trader:
            return False
        current = snapshot.net_quantity(order.instrument_id)
        if current == 0:
            return False
        opposite_side = (current > 0) != (order.signed_quantity > 0)
        return opposite_side and abs(order.signed_quantity) <= abs(current)

    def _market_reasons(
        self,
        order: order_request_module.OrderRequest,
        limits: trading_limits_module.TradingLimits | None,
        now: datetime.datetime,
    ) -> list[str]:
        """Checks that the exchange is open for an ordinary order, and closed for an after-market order.

        Args:
            order (order_request_module.OrderRequest): The order.
            limits (trading_limits_module.TradingLimits | None): The limits, or None when they cannot be read.
            now (datetime.datetime): The current time.

        Returns:
            list[str]: A reason when the order does not suit the exchange's state, otherwise nothing.
        """
        is_open, description = self._services.exchange_hours.is_open(
            order.exchange,
            order.segment,
            now,
            self._trading_window(limits),
        )
        if order.after_market and is_open:
            return [
                f'The exchange is open ({description}), so place an ordinary order instead of an after-market order.',
            ]
        if order.after_market:
            return []
        if is_open:
            return []
        return [
            f'New orders are not allowed now: {description}.',
        ]

    def _ownership_reasons(
        self,
        order: order_request_module.OrderRequest,
        snapshot: account_snapshot_module.AccountSnapshot,
    ) -> list[str]:
        """Checks that no other trader, and not the user outside the agent, holds the instrument.

        Args:
            order (order_request_module.OrderRequest): The order.
            snapshot (account_snapshot_module.AccountSnapshot): The account now.

        Returns:
            list[str]: A reason when the instrument belongs to someone else, otherwise nothing.
        """
        owner = self._services.ledger.owner(order.instrument_id)
        if owner is not None and owner != order.trader:
            return [
                f'{order.symbol} belongs to the {owner} trader; one trader trades an instrument at a time.',
            ]
        held = order.instrument_id in snapshot.held_instrument_ids()
        is_cash = _CASH_SEGMENT_WORD in order.segment
        if is_cash and order.symbol.upper() in snapshot.held_symbols:
            held = True
        if held and owner is None:
            return [
                f"{order.symbol} is already held in the account outside the agent (the user's own position or holding), so no trader may trade it.",
            ]
        return []

    def _opening_reasons(
        self,
        order: order_request_module.OrderRequest,
        limits: trading_limits_module.TradingLimits,
        snapshot: account_snapshot_module.AccountSnapshot,
        margin: float,
        now: datetime.datetime,
    ) -> list[str]:
        """Checks an order that opens or enlarges a position against every limit.

        Args:
            order (order_request_module.OrderRequest): The order.
            limits (trading_limits_module.TradingLimits): The limits.
            snapshot (account_snapshot_module.AccountSnapshot): The account now.
            margin (float): The order's estimated margin.
            now (datetime.datetime): The current time.

        Returns:
            list[str]: Every limit the order breaks.
        """
        account = limits.account
        trader = limits.trader(order.trader)
        reasons = []
        today = now.date()
        account_halt = self._services.ledger.active_halt(
            risk_ledger_module.ACCOUNT_SCOPE, today
        )
        if account_halt is not None:
            reasons.append(
                f'Trading is halted for the account: {account_halt} Only orders that close your own positions are allowed.'
            )
        trader_halt = self._services.ledger.active_halt(order.trader, today)
        if trader_halt is not None:
            reasons.append(f'Trading is halted for this trader: {trader_halt}')
        if not account.trading_enabled:
            reasons.append(
                'trading_enabled is false in TradingRules.md, so no new position may be opened.'
            )
        if (
            trader.allowed_products
            and order.product not in trader.allowed_products
        ):
            reasons.append(
                f'Product {order.product} is not allowed for this trader; allowed: {", ".join(trader.allowed_products)}.'
            )
        if trader.allowed_instruments and order.symbol.upper() not in [
            symbol.upper() for symbol in trader.allowed_instruments
        ]:
            reasons.append(
                f"{order.symbol} is not in this trader's allowed instruments."
            )
        if (
            order.is_option
            and order.transaction_type == 'sell'
            and not account.allow_option_writing
        ):
            reasons.append(
                'Selling an option to open or enlarge a short position is option writing, which allow_option_writing = false forbids.'
            )
        balance = snapshot.total_balance
        order_cap = account.maximum_order_value_percent / 100 * balance
        if margin > order_cap:
            reasons.append(
                f'The order would block about {margin:,.2f} of margin, above the per-order cap of {account.maximum_order_value_percent:g}% of {balance:,.2f} = {order_cap:,.2f}.'
            )
        capital = account.capital_percent / 100 * balance
        free_capital = capital - snapshot.margin_utilized
        if margin > free_capital:
            reasons.append(
                f"The order would block about {margin:,.2f}, more than the {free_capital:,.2f} of the agent's capital still free ({account.capital_percent:g}% of {balance:,.2f}, less {snapshot.margin_utilized:,.2f} in use)."
            )
        if trader.capital_share_percent is not None:
            trader_capital = trader.capital_share_percent / 100 * capital
            trader_margin = self._trader_margin(order.trader, snapshot)
            if trader_margin + margin > trader_capital:
                reasons.append(
                    f"The trader's positions block about {trader_margin:,.2f}; with this order that exceeds its {trader.capital_share_percent:g}% share, {trader_capital:,.2f}."
                )
        if account.maximum_open_positions is not None:
            held = snapshot.held_instrument_ids()
            if (
                order.instrument_id not in held
                and len(held) >= account.maximum_open_positions
            ):
                reasons.append(
                    f'{len(held)} instruments are already held, the most maximum_open_positions allows.'
                )
        if trader.maximum_orders_per_minute is not None:
            recent = self._services.ledger.approvals_since(
                order.trader, now - _ONE_MINUTE
            )
            if recent >= trader.maximum_orders_per_minute:
                reasons.append(
                    f'This trader has sent {recent} orders in the last minute, its maximum.'
                )
        return reasons

    def _trader_margin(
        self,
        trader: str,
        snapshot: account_snapshot_module.AccountSnapshot,
    ) -> float:
        """Estimates the margin a trader's open positions block.

        Args:
            trader (str): The trader.
            snapshot (account_snapshot_module.AccountSnapshot): The account now.

        Returns:
            float: The estimated margin in rupees.
        """
        owned = self._services.ledger.owned_by(trader)
        total = 0.0
        for row in snapshot.positions:
            if row.instrument_id not in owned or row.quantity == 0:
                continue
            position_as_order = order_request_module.OrderRequest(
                trader=trader,
                instrument_id=row.instrument_id,
                exchange='',
                segment=row.segment,
                symbol=row.symbol,
                transaction_type='buy' if row.quantity > 0 else 'sell',
                quantity=abs(row.quantity),
                product=_POSITION_PRODUCTS.get(row.product, 'nrml'),
                price=row.last_price,
            )
            total += self._services.margin_estimator.margin(position_as_order)
        return total

    def _finish(
        self,
        order: order_request_module.OrderRequest,
        reasons: list[str],
        margin: float,
    ) -> RiskDecision:
        """Publishes the decision and returns it.

        Args:
            order (order_request_module.OrderRequest): The order.
            reasons (list[str]): Why it was refused; empty when approved.
            margin (float): Its estimated margin.

        Returns:
            RiskDecision: The decision.
        """
        decision = RiskDecision(
            approved=not reasons,
            reasons=tuple(reasons),
            estimated_margin=margin,
        )
        self._event_bus.publish(
            event_module.Event.now(
                event_module.EventKind.RISK_DECISION,
                order.trader,
                {
                    'order': order.describe(),
                    'instrument_id': order.instrument_id,
                    'approved': decision.approved,
                    'reasons': list(decision.reasons),
                    'estimated_margin': round(margin, 2),
                },
            )
        )
        return decision

    def _real_now(self) -> datetime.datetime:
        """The current time in UTC.

        Returns:
            datetime.datetime: Now.
        """
        return datetime.datetime.now(datetime.UTC)
