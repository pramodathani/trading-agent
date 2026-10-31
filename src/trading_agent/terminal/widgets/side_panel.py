"""The right-hand panel of the chat: eight cards about the trader, as on the web page.

The panel reads the gateway on the web page's timings: the context window every 20 seconds and after a turn, a compression, a new session or a model switch; the account and the traders' open orders every 15 seconds and after an order, a fill, a halt or the kill switch; the MCP servers every minute. The counts of orders and the outputs come from the trader's events of today, which the chat screen passes on. Which cards are folded is remembered between runs.

Typical usage example:

  panel = SidePanel(gateway, settings, opener)
  panel.set_trader('general')
  panel.take_events(events)
"""

from typing import Any

from textual import containers
from textual import widgets
from textual import work

from trading_agent.terminal import attachment_opener
from trading_agent.terminal import gateway_client
from trading_agent.terminal import terminal_settings
from trading_agent.terminal.widgets import context_card
from trading_agent.terminal.widgets import funds_card
from trading_agent.terminal.widgets import model_card
from trading_agent.terminal.widgets import orders_card
from trading_agent.terminal.widgets import outputs_card
from trading_agent.terminal.widgets import profit_card
from trading_agent.terminal.widgets import side_card
from trading_agent.terminal.widgets import tools_card
from trading_agent.terminal.widgets import trader_card

_ACCOUNT_REFRESH_SECONDS = 15.0
_CONTEXT_REFRESH_SECONDS = 20.0
_SERVERS_REFRESH_SECONDS = 60.0
_CONTEXT_CHANGING_KINDS = (
    'turn_finished',
    'context_compressed',
    'session_started',
    'backend_switch',
)
_ACCOUNT_CHANGING_KINDS = (
    'order',
    'fill',
    'trader_halt',
    'kill_switch',
)


class SidePanel(containers.VerticalScroll):
    """The side panel."""

    def __init__(
        self,
        gateway: gateway_client.GatewayClient,
        settings: terminal_settings.TerminalSettings,
        opener: attachment_opener.AttachmentOpener,
    ):
        """Creates the panel and its cards.

        Args:
            gateway (gateway_client.GatewayClient): The gateway's routes.
            settings (terminal_settings.TerminalSettings): The remembered choices, holding the folded cards.
            opener (attachment_opener.AttachmentOpener): Downloads and opens the trader's files.
        """
        super().__init__(id='side-panel')
        self._gateway = gateway
        self._settings = settings
        folded = set(settings.collapsed_cards)
        self._trader_card = trader_card.TraderCard('trader' in folded)
        self._model_card = model_card.ModelCard('model' in folded)
        self._context_card = context_card.ContextCard('context' in folded)
        self._funds_card = funds_card.FundsCard('funds' in folded)
        self._profit_card = profit_card.ProfitCard('pnl' in folded)
        self._orders_card = orders_card.OrdersCard('orders' in folded)
        self._tools_card = tools_card.ToolsCard('tools' in folded)
        self._outputs_card = outputs_card.OutputsCard(
            opener, 'outputs' in folded
        )
        self._trader_name = ''
        self._mode = ''
        self._trader: dict[str, Any] | None = None
        self._events: list[dict[str, Any]] = []
        self._context_document: dict[str, Any] | None = None
        self._account: dict[str, Any] | None = None
        self._trader_orders: dict[str, Any] | None = None
        self._servers: list[dict[str, Any]] | None = None

    def compose(self):
        """Builds the panel.

        Yields:
            Widget: The eight cards.
        """
        yield self._trader_card
        yield self._model_card
        yield self._context_card
        yield self._funds_card
        yield self._profit_card
        yield self._orders_card
        yield self._tools_card
        yield self._outputs_card

    def on_mount(self) -> None:
        """Starts the timers that read the gateway."""
        self.set_interval(_CONTEXT_REFRESH_SECONDS, self.refresh_context)
        self.set_interval(_ACCOUNT_REFRESH_SECONDS, self.refresh_account)
        self.set_interval(_SERVERS_REFRESH_SECONDS, self.refresh_servers)
        self.refresh_account()
        self.refresh_servers()

    def set_trader(self, trader_name: str) -> None:
        """Shows another trader, forgetting the previous trader's events.

        Args:
            trader_name (str): The trader.
        """
        self._trader_name = trader_name
        self._events = []
        self._context_document = None
        self._show_all()
        self.refresh_context()

    def take_events(self, events: list[dict[str, Any]]) -> None:
        """Takes the trader's new events and reads the gateway again when they change something.

        Args:
            events (list[dict[str, Any]]): The events, oldest first.
        """
        context_changed = False
        account_changed = False
        for event in events:
            kind = event.get('kind')
            if kind == 'text_delta':
                continue
            self._events.append(event)
            if kind in _CONTEXT_CHANGING_KINDS:
                context_changed = True
            if kind in _ACCOUNT_CHANGING_KINDS:
                account_changed = True
        if context_changed:
            self.refresh_context()
        if account_changed:
            self.refresh_account()
        self._show_events()

    def take_trader(self, trader: dict[str, Any] | None, mode: str) -> None:
        """Shows the trader's state and models.

        Args:
            trader (dict[str, Any] | None): The trader summary, or None while loading.
            mode (str): "dry_run" or "live".
        """
        self._trader = trader
        self._mode = mode
        self._trader_card.show(trader, mode)
        self._show_model()

    def on_collapsible_collapsed(
        self, event: widgets.Collapsible.Collapsed
    ) -> None:
        """Remembers that a card was folded.

        Args:
            event (widgets.Collapsible.Collapsed): The fold.
        """
        self._remember(event.collapsible, True)

    def on_collapsible_expanded(
        self, event: widgets.Collapsible.Expanded
    ) -> None:
        """Remembers that a card was opened.

        Args:
            event (widgets.Collapsible.Expanded): The opening.
        """
        self._remember(event.collapsible, False)

    @work(exclusive=True, group='side-context')
    async def refresh_context(self) -> None:
        """Reads the trader's context window and tools."""
        if not self._trader_name:
            return
        trader_name = self._trader_name
        try:
            document = await self._gateway.trader_context(trader_name)
        except gateway_client.GatewayError as error:
            self._context_card.show(None, error.message)
            return
        if trader_name != self._trader_name:
            return
        self._context_document = document
        self._context_card.show(document.get('usage'), None)
        self._show_model()
        self._show_tools()

    @work(exclusive=True, group='side-account')
    async def refresh_account(self) -> None:
        """Reads the account and the traders' open orders."""
        try:
            self._account = await self._gateway.account()
        except gateway_client.GatewayError as error:
            self._funds_card.show(None, error.message)
            return
        try:
            self._trader_orders = await self._gateway.trader_orders()
        except gateway_client.GatewayError:
            self._trader_orders = None
        self._funds_card.show(self._account, None)
        self._profit_card.show(self._trader_name, self._account)
        self._show_events()

    @work(exclusive=True, group='side-servers')
    async def refresh_servers(self) -> None:
        """Reads the MCP servers."""
        try:
            answer = await self._gateway.mcp_servers()
        except gateway_client.GatewayError:
            return
        self._servers = answer.get('servers') or []
        self._show_tools()

    def _show_all(self) -> None:
        """Redraws every card from what is known."""
        self._trader_card.show(self._trader, self._mode)
        self._show_model()
        self._context_card.show(None, None)
        self._funds_card.show(self._account, None)
        self._profit_card.show(self._trader_name, self._account)
        self._show_tools()
        self._show_events()

    def _show_model(self) -> None:
        """Redraws the Model card."""
        usage = None
        if self._context_document is not None:
            usage = self._context_document.get('usage')
        self._model_card.show(self._trader, usage)

    def _show_tools(self) -> None:
        """Redraws the Tools card."""
        tools = []
        if self._context_document is not None:
            tools = list(self._context_document.get('tools') or [])
        self._tools_card.show(tools, self._servers)

    def _show_events(self) -> None:
        """Redraws the cards that count today's events."""
        open_orders = None
        if self._trader_orders is not None:
            open_orders = self._trader_orders.get(self._trader_name) or []
        self._orders_card.show(
            self._trader_name, self._events, open_orders, self._account
        )
        self._outputs_card.show(self._trader_name, self._events)

    def _remember(self, collapsible: widgets.Collapsible, folded: bool) -> None:
        """Saves whether a card is folded.

        Args:
            collapsible (widgets.Collapsible): The card or a fold inside it.
            folded (bool): Whether it is folded now.
        """
        if not isinstance(collapsible, side_card.SideCard):
            return
        cards = set(self._settings.collapsed_cards)
        if folded:
            cards.add(collapsible.card_id)
        else:
            cards.discard(collapsible.card_id)
        self._settings.collapsed_cards = sorted(cards)
        self._settings.save()
