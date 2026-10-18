"""The terminal program: a full-screen chat with the desks of a running gateway, like Claude Code.

It is a client of the gateway, as the web page is. One event stream connection carries every live event; the desks' states are read every 5 seconds and again after events that change them.

Typical usage example:

  application = TerminalApplication(gateway, settings, history)
  application.run()
"""

from typing import Any, ClassVar

from textual import app
from textual import binding
from textual import work

from trading_agent.terminal import attachment_opener
from trading_agent.terminal import event_stream
from trading_agent.terminal import gateway_client
from trading_agent.terminal import prompt_history as prompt_history_module
from trading_agent.terminal import terminal_settings
from trading_agent.terminal import terminal_themes
from trading_agent.terminal.screens import chat_screen

_DESKS_REFRESH_SECONDS = 5.0
_DESK_CHANGING_KINDS = (
    'trigger_received',
    'turn_started',
    'turn_finished',
    'session_started',
    'backend_switch',
    'stopped',
)
_DEFAULT_DESK = 'general'


class TerminalApplication(app.App[int]):
    """The terminal program."""

    CSS_PATH = 'styles/terminal.tcss'
    TITLE = 'trading-agent'
    ENABLE_COMMAND_PALETTE = True
    BINDINGS: ClassVar[list[binding.BindingType]] = [
        binding.Binding('ctrl+q', 'quit', 'Quit', show=False),
    ]

    def __init__(
        self,
        gateway: gateway_client.GatewayClient,
        settings: terminal_settings.TerminalSettings,
        history: prompt_history_module.PromptHistory,
        desk_name: str | None = None,
    ):
        """Creates the program without connecting.

        Args:
            gateway (gateway_client.GatewayClient): The gateway's routes.
            settings (terminal_settings.TerminalSettings): The remembered choices.
            history (prompt_history_module.PromptHistory): The earlier prompts.
            desk_name (str | None): The desk to open on, or None for the one used last.
        """
        super().__init__()
        self._gateway = gateway
        self._settings = settings
        self._history = history
        self._theme_set = terminal_themes.TerminalThemes()
        self._first_desk = desk_name or settings.desk or _DEFAULT_DESK
        self.chat: chat_screen.ChatScreen | None = None
        self.desks_document: dict[str, Any] = {}
        self.problem: str | None = None

    def on_mount(self) -> None:
        """Applies the theme, opens the chat, and starts the event stream and the desk polling."""
        for theme in self._theme_set.all():
            self.register_theme(theme)
        self.theme = self._settings.theme
        self.chat = chat_screen.ChatScreen(
            self._gateway,
            self._history,
            self._first_desk,
            self._settings,
            attachment_opener.AttachmentOpener(self._gateway),
        )
        self.push_screen(self.chat)
        self._follow_events()
        self.refresh_desks()
        self.set_interval(_DESKS_REFRESH_SECONDS, self.refresh_desks)

    async def on_unmount(self) -> None:
        """Closes the gateway client's connections."""
        await self._gateway.close()

    @work(exclusive=True, group='desks')
    async def refresh_desks(self) -> None:
        """Reads the desks' states and passes them to the chat."""
        try:
            document = await self._gateway.desks()
        except gateway_client.GatewayError as error:
            if error.status_code == 401:
                self._refuse()
            return
        self.desks_document = document
        if self.chat is not None:
            self.chat.take_desks(document)

    def remember_desk(self, desk_name: str) -> None:
        """Remembers the desk the chat shows, for the next run.

        Args:
            desk_name (str): The desk.
        """
        self._settings.desk = desk_name
        self._settings.save()

    def toggle_theme(self) -> None:
        """Switches between the dark and light theme and remembers the choice."""
        self.theme = self._theme_set.other(self.theme)
        self._settings.theme = self.theme
        self._settings.save()

    def action_toggle_theme(self) -> None:
        """Switches between the dark and light theme."""
        self.toggle_theme()

    @work(exclusive=True, group='events')
    async def _follow_events(self) -> None:
        """Passes every live event on until the program ends."""
        stream = event_stream.EventStream(self._gateway.events_address())
        try:
            await stream.follow(self._take_event, self._take_connection)
        except event_stream.AccessRefusedError:
            self._refuse()

    def _take_event(self, event: dict[str, Any]) -> None:
        """Passes one live event to the chat.

        Args:
            event (dict[str, Any]): The event.
        """
        if self.chat is not None:
            self.chat.take_event(event)
        if event.get('kind') in _DESK_CHANGING_KINDS:
            self.refresh_desks()

    def _take_connection(self, state: str) -> None:
        """Passes the event stream's state to the chat.

        Args:
            state (str): The state.
        """
        if self.chat is not None:
            self.chat.take_connection(state)
        if state == event_stream.LIVE:
            self.refresh_desks()

    def _refuse(self) -> None:
        """Ends the program because the gateway refused the access token."""
        self.problem = 'The gateway refused the access token. Check TRADING_AGENT_GATEWAY_ACCESS_TOKEN in .env.'
        self.exit(1)
