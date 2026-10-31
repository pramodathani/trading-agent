"""The shallow base class of the tools that place, change, cancel and close orders.

Every order tool asks the risk engine before it sends anything that adds risk, tags each order with the trader's name, records the order in the trader order book, and publishes what it did on the event bus, where the journal keeps it with the model's stated reason. In dry_run mode every request goes to UBI as a dry run, which UBI checks and answers without sending anything to a broker.

Typical usage example:

  class PlaceOrderTool(OrderTool):
      async def _act(self, arguments):
          ...
"""

import dataclasses
import functools
import uuid
from typing import Any

import pydantic
from tradingmachine.assets import exceptions as instrument_exceptions
from tradingmachine.assets import instruments
from tradingmachine.unified_broker_interface import exceptions as ubi_exceptions

from trading_agent.risk import account_snapshot as account_snapshot_module
from trading_agent.risk import order_request as order_request_module
from trading_agent.risk import risk_engine as risk_engine_module
from trading_agent.risk import risk_ledger as risk_ledger_module
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.tools import tool
from trading_agent.trading import broker_reader as broker_reader_module
from trading_agent.trading import instrument_arguments
from trading_agent.trading import result_formatter as result_formatter_module
from trading_agent.trading import trader_order_book as trader_order_book_module

_ORDER_TIMEOUT_SECONDS = 120.0
_TAG_LENGTH = 20
_DRY_RUN_PREFIX = 'dry-'


@dataclasses.dataclass(frozen=True)
class OrderServices:
    """What the order tools use, shared by every trader.

    Attributes:
        reader: The shared reader of UBI, whose lock every UBI call goes through.
        risk_engine: The engine every order that adds risk must pass.
        order_book: The record of which trader placed which order.
        snapshot_reader: Reads the account's positions, for closing a trader's positions.
        ledger: The risk ledger, for the instruments a trader owns.
        event_bus: Where every order action is published.
        formatter: Turns UBI's answers into text.
    """

    reader: broker_reader_module.BrokerReader
    risk_engine: risk_engine_module.RiskEngine
    order_book: trader_order_book_module.TraderOrderBook
    snapshot_reader: account_snapshot_module.AccountSnapshotReader
    ledger: risk_ledger_module.RiskLedger
    event_bus: event_bus_module.EventBus
    formatter: result_formatter_module.ResultFormatter


class OrderTool(tool.Tool):
    """A tool that sends orders, or changes or cancels them, for one trader."""

    timeout_seconds = _ORDER_TIMEOUT_SECONDS

    def __init__(self, services: OrderServices, trader: str, mode: str):
        """Creates the tool.

        Args:
            services (OrderServices): What the tool uses.
            trader (str): The trader the tool works for.
            mode (str): "dry_run" to send everything to UBI as a dry run, "live" to trade.
        """
        self._services = services
        self._trader = trader
        self._dry_run = mode != 'live'
        tag_characters = []
        for character in trader:
            if character.isalnum():
                tag_characters.append(character)
        self._tag = ''.join(tag_characters)[:_TAG_LENGTH]

    async def run(self, arguments: pydantic.BaseModel) -> tool.ToolResult:
        """Does the tool's work, and explains any failure in words the model can act on.

        Args:
            arguments (pydantic.BaseModel): The checked arguments.

        Returns:
            tool.ToolResult: What happened, or why it could not happen.
        """
        try:
            return await self._act(arguments)
        except ubi_exceptions.OrderOutcomeUnknownError as error:
            return tool.ToolResult.error(
                f'UBI did not answer in time, so the request may still have gone through: {error}. Check get_orders before trying again, or the order may be sent twice.'
            )
        except instrument_exceptions.InstrumentError as error:
            return tool.ToolResult.error(
                f'Instrument problem: {error}. Check the fields, or find the instrument with search_instruments.'
            )
        except ubi_exceptions.UnifiedBrokerInterfaceError as error:
            return tool.ToolResult.error(
                f'UBI refused or failed the request: {type(error).__name__}: {error}'
            )

    async def _act(self, arguments: pydantic.BaseModel) -> tool.ToolResult:
        """Does the tool's own work. Subclasses override it.

        Args:
            arguments (pydantic.BaseModel): The checked arguments.

        Returns:
            tool.ToolResult: What happened.

        Raises:
            NotImplementedError: Always, because subclasses must override this method.
        """
        raise NotImplementedError

    async def _instrument(
        self,
        arguments: instrument_arguments.InstrumentArguments,
    ) -> instruments.TradeableInstrument:
        """Looks up the instrument the model named.

        Args:
            arguments (instrument_arguments.InstrumentArguments): How the model named it.

        Returns:
            instruments.TradeableInstrument: The instrument.
        """
        reader = self._services.reader
        return await reader.call(
            functools.partial(reader.tradeable_instrument, arguments)
        )

    async def _instrument_by_id(
        self, instrument_id: str
    ) -> instruments.TradeableInstrument:
        """Looks up an instrument by UBI's id.

        Args:
            instrument_id (str): UBI's id.

        Returns:
            instruments.TradeableInstrument: The instrument.
        """
        return await self._instrument(
            instrument_arguments.InstrumentArguments(
                instrument_id=instrument_id
            )
        )

    def _lot_problem(
        self,
        instrument: instruments.TradeableInstrument,
        quantity: int,
    ) -> str | None:
        """Checks that a quantity is a whole number of lots.

        Args:
            instrument (instruments.TradeableInstrument): The instrument.
            quantity (int): The quantity in units.

        Returns:
            str | None: The problem, or None when the quantity is fine.
        """
        lot_size = instrument.lot_size
        if lot_size is None or lot_size <= 1:
            return None
        if quantity % lot_size == 0:
            return None
        return f'The quantity {quantity} is not a whole number of lots: one lot of this instrument is {lot_size} units, so use a multiple of {lot_size}.'

    async def _valuation_price(
        self,
        instrument: instruments.TradeableInstrument,
        price: float | None,
        trigger_price: float | None,
    ) -> float | None:
        """The price an order is valued at: its limit price, else its trigger price, else the last traded price.

        Args:
            instrument (instruments.TradeableInstrument): The instrument.
            price (float | None): The order's limit price, or None.
            trigger_price (float | None): The order's trigger price, or None.

        Returns:
            float | None: The price, or None when the order has neither and no last price is known.
        """
        if price is not None:
            return price
        if trigger_price is not None:
            return trigger_price
        return await self._services.reader.call(
            functools.partial(self._last_price, instrument)
        )

    def _last_price(
        self, instrument: instruments.TradeableInstrument
    ) -> float | None:
        """Reads an instrument's last traded price. It runs in a worker thread, under the UBI lock.

        Args:
            instrument (instruments.TradeableInstrument): The instrument.

        Returns:
            float | None: The price, or None when UBI has none.
        """
        return instrument.last_price

    def _order_request(
        self,
        instrument: instruments.TradeableInstrument,
        transaction_type: str,
        quantity: int,
        product: str,
        price: float,
    ) -> order_request_module.OrderRequest:
        """Describes an order for the risk engine.

        Args:
            instrument (instruments.TradeableInstrument): The instrument.
            transaction_type (str): "buy" or "sell".
            quantity (int): How many units.
            product (str): "cnc", "mis" or "nrml".
            price (float): The price the order is valued at.

        Returns:
            order_request_module.OrderRequest: The request.
        """
        symbol = instrument.symbol or instrument.underlying_symbol or ''
        return order_request_module.OrderRequest(
            trader=self._trader,
            instrument_id=instrument.instrument_id,
            exchange=instrument.exchange,
            segment=instrument.segment,
            symbol=symbol,
            transaction_type=transaction_type,
            quantity=quantity,
            product=product,
            price=price,
        )

    def _refusal(
        self,
        request: order_request_module.OrderRequest,
        decision: risk_engine_module.RiskDecision,
    ) -> tool.ToolResult:
        """Explains why the risk engine refused an order.

        Args:
            request (order_request_module.OrderRequest): The order.
            decision (risk_engine_module.RiskDecision): The engine's decision.

        Returns:
            tool.ToolResult: An error listing every reason.
        """
        lines = [
            f'The risk engine refused the order ({request.describe()}). Nothing was sent. The reasons:',
        ]
        for reason in decision.reasons:
            lines.append(f'- {reason}')
        return tool.ToolResult.error('\n'.join(lines))

    def _remember(
        self,
        kind: str,
        request: order_request_module.OrderRequest,
        answer: Any,
    ) -> trader_order_book_module.OrderRecord:
        """Records a placed order in the trader order book.

        Args:
            kind (str): "order", "bracket" or "close".
            request (order_request_module.OrderRequest): The order.
            answer (Any): UBI's answer to placing it.

        Returns:
            trader_order_book_module.OrderRecord: The record.
        """
        if not isinstance(answer, dict):
            answer = {}
        parent_id = answer.get('parent_id')
        order_id = answer.get('order_id')
        if parent_id is None and order_id is None:
            parent_id = f'{_DRY_RUN_PREFIX}{uuid.uuid4().hex[:12]}'
        record_id = parent_id or order_id
        record = trader_order_book_module.OrderRecord(
            record_id=record_id,
            trader=self._trader,
            kind=kind,
            parent_id=parent_id,
            order_id=order_id,
            instrument_id=request.instrument_id,
            exchange=request.exchange,
            segment=request.segment,
            symbol=request.symbol,
            transaction_type=request.transaction_type,
            quantity=request.quantity,
            product=request.product,
            price=request.price,
            dry_run=self._dry_run,
            state=trader_order_book_module.OPEN,
            placed_at=trader_order_book_module.TraderOrderBook.now_text(),
        )
        self._services.order_book.add(record)
        return record

    def _publish(self, details: dict[str, Any]) -> None:
        """Publishes an order action for the journal and the interfaces.

        Args:
            details (dict[str, Any]): What happened; the trader and the mode are added.
        """
        payload = {
            'dry_run': self._dry_run,
        }
        payload.update(details)
        self._services.event_bus.publish(
            event_module.Event.now(
                event_module.EventKind.ORDER,
                self._trader,
                payload,
            )
        )

    def _mode_note(self) -> str:
        """One sentence that says whether the action was real.

        Returns:
            str: The sentence.
        """
        if self._dry_run:
            return 'This was a dry run: UBI checked the request and sent nothing to a broker.'
        return 'This was live: the request went to UBI and its brokers.'

    def _answer_text(self, answer: Any) -> str:
        """UBI's answer as text.

        Args:
            answer (Any): The answer.

        Returns:
            str: The text.
        """
        return self._services.formatter.format(answer)
