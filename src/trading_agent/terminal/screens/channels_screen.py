"""The Channels page: the Telegram channel's state, the chats waiting to be paired, and the paired chats.

It copies the web page's ChannelsPage.tsx: a waiting pairing is approved with a, a code can be typed, and a paired chat is revoked with Delete.

Typical usage example:

  app.push_screen(ChannelsScreen('general'))
"""

from typing import ClassVar

from textual import binding
from textual import containers
from textual import widgets
from textual import work
from textual.content import Content

from trading_agent.terminal import formatter
from trading_agent.terminal import gateway_client
from trading_agent.terminal.screens import page_screen


class ChannelsScreen(page_screen.PageScreen):
    """The Channels page."""

    TITLE_TEXT = 'Channels'
    REFRESH_SECONDS = 10.0

    BINDINGS: ClassVar[list[binding.BindingType]] = [
        binding.Binding('a', 'approve', 'Approve pairing'),
        binding.Binding('delete', 'revoke', 'Revoke chat'),
    ]

    def compose_page(self):
        """Builds the status, the pairing tables and the code box.

        Yields:
            Widget: The sections, in a scroll area.
        """
        with containers.VerticalScroll(classes='page-body'):
            yield widgets.Static(
                '', id='channels-status', classes='page-summary'
            )
            yield widgets.Static(
                '[b]Waiting to be paired[/b] [dim]a approves[/dim]',
                classes='page-heading',
            )
            yield widgets.DataTable(id='channels-pending', cursor_type='row')
            yield widgets.Input(
                placeholder='Or type the code the bot sent, then press enter',
                id='channels-code',
            )
            yield widgets.Static(
                '[b]Paired chats[/b] [dim]delete revokes[/dim]',
                classes='page-heading',
            )
            yield widgets.DataTable(id='channels-paired', cursor_type='row')

    def on_mount(self) -> None:
        """Sets up the tables, then reads the channel."""
        self.table('channels-pending').add_columns(
            'Code', 'Name', 'Chat', 'Asked'
        )
        self.table('channels-paired').add_columns(
            'Name', 'Chat', 'Trader', 'Paired'
        )
        super().on_mount()

    @work(exclusive=True, group='page')
    async def refresh_page(self) -> None:
        """Reads the Telegram channel."""
        try:
            telegram = await self.app.gateway.telegram()
        except gateway_client.GatewayError as error:
            self.problem(error.message)
            return
        clock = formatter.Formatter()
        state = str(telegram.get('state', ''))
        if telegram.get('error'):
            state += f' ({telegram["error"]})'
        self.query_one('#channels-status', widgets.Static).update(
            Content.from_markup(
                'Telegram [b]$enabled[/b] · token $token · state [b]$state[/b] · @$name · default trader $trader\n[dim]Notifications: $notifications[/dim]',
                enabled='on' if telegram.get('enabled') else 'off',
                token='set' if telegram.get('token_present') else 'missing',
                state=state,
                name=str(telegram.get('username') or '—'),
                trader=str(telegram.get('default_trader', '')),
                notifications=', '.join(
                    str(item) for item in telegram.get('notifications') or []
                ),
            )
        )
        pending = self.table('channels-pending')
        pending.clear()
        for item in telegram.get('pending') or []:
            pending.add_row(
                str(item.get('code', '')),
                str(item.get('name', '')),
                str(item.get('chat_id', '')),
                clock.day_time(
                    str(
                        item.get('requested_at') or item.get('created_at') or ''
                    )
                ),
                key=str(item.get('code', '')),
            )
        paired = self.table('channels-paired')
        paired.clear()
        for chat in telegram.get('paired') or []:
            paired.add_row(
                str(chat.get('name', '')),
                str(chat.get('chat_id', '')),
                str(chat.get('trader', '')),
                clock.day_time(str(chat.get('paired_at', ''))),
                key=str(chat.get('chat_id', '')),
            )

    def action_approve(self) -> None:
        """Approves the highlighted pairing."""
        code = self.selected_key('channels-pending')
        if code is not None:
            self._approve(code)

    def on_input_submitted(self, event: widgets.Input.Submitted) -> None:
        """Approves a typed code.

        Args:
            event (widgets.Input.Submitted): The code.
        """
        event.stop()
        if event.value.strip():
            self._approve(event.value.strip())
            event.input.value = ''

    def action_revoke(self) -> None:
        """Revokes the highlighted paired chat."""
        chat_id = self.selected_key('channels-paired')
        if chat_id is not None and self.focused is self.table(
            'channels-paired'
        ):
            self._revoke(int(chat_id))

    @work(group='action')
    async def _approve(self, code: str) -> None:
        """Pairs the chat a code belongs to.

        Args:
            code (str): The pairing code.
        """
        try:
            await self.app.gateway.approve_pairing(code)
        except gateway_client.GatewayError as error:
            self.problem(error.message)
            return
        self.notify('Paired.', timeout=3)
        self.refresh_page()

    @work(group='action')
    async def _revoke(self, chat_id: int) -> None:
        """Unpairs a chat.

        Args:
            chat_id (int): The chat.
        """
        try:
            await self.app.gateway.revoke_pairing(chat_id)
        except gateway_client.GatewayError as error:
            self.problem(error.message)
            return
        self.notify('Unpaired; the bot now ignores that chat.', timeout=3)
        self.refresh_page()
