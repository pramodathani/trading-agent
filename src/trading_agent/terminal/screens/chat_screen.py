"""The chat with one desk: today's turns, the live progress line and the message box.

The screen reads today's journal of the desk when it opens, then takes live events from the application. Events that arrive while the journal is still loading are held and added afterwards; ChatTranscript drops the ones the journal already had.

The terminal program's own commands (/desk, /model with no name, /theme, /keys, /exit) are handled here. Every other message, including every other /command, goes to the desk, which answers commands such as /status itself.

Typical usage example:

  app.push_screen(ChatScreen(gateway, history, 'general'))
"""

import time
from typing import Any, ClassVar

from textual import binding
from textual import containers
from textual import screen
from textual import widgets
from textual import work
from textual.content import Content

from trading_agent.terminal import chat_items
from trading_agent.terminal import chat_transcript
from trading_agent.terminal import event_stream
from trading_agent.terminal import gateway_client
from trading_agent.terminal import model_names
from trading_agent.terminal import prompt_history as prompt_history_module
from trading_agent.terminal.widgets import command_menu
from trading_agent.terminal.widgets import composer as composer_module
from trading_agent.terminal.widgets import desk_picker
from trading_agent.terminal.widgets import event_step_view
from trading_agent.terminal.widgets import history_search
from trading_agent.terminal.widgets import keys_screen
from trading_agent.terminal.widgets import model_picker
from trading_agent.terminal.widgets import progress_line
from trading_agent.terminal.widgets import turn_view

_DOUBLE_PRESS_SECONDS = 1.5
_BOTTOM_SLACK_LINES = 3
_CONNECTION_WORDS = {
    event_stream.CONNECTING: 'Connecting…',
    event_stream.LIVE: 'Live',
    event_stream.RECONNECTING: 'Reconnecting…',
    event_stream.REFUSED: 'Token refused',
}
_TERMINAL_COMMANDS = (
    '/desk',
    '/theme',
    '/keys',
    '/exit',
    '/quit',
)


class ChatScreen(screen.Screen[None]):
    """The chat screen."""

    BINDINGS: ClassVar[list[binding.BindingType]] = [
        binding.Binding('escape', 'escape', 'Stop', show=False),
        binding.Binding('ctrl+c', 'interrupt', 'Clear or exit', priority=True),
        binding.Binding('ctrl+d', 'exit_when_empty', 'Exit', priority=True),
        binding.Binding('alt+d', 'pick_desk', 'Desk'),
        binding.Binding('alt+p', 'pick_model', 'Model'),
        binding.Binding('ctrl+o', 'toggle_tools', 'Tools'),
        binding.Binding('ctrl+r', 'search_history', 'History'),
        binding.Binding('ctrl+t', 'app.toggle_theme', 'Theme'),
    ]

    def __init__(
        self,
        gateway: gateway_client.GatewayClient,
        history: prompt_history_module.PromptHistory,
        desk_name: str,
    ):
        """Creates the screen.

        Args:
            gateway (gateway_client.GatewayClient): The gateway's routes.
            history (prompt_history_module.PromptHistory): The earlier prompts.
            desk_name (str): The desk to open on.
        """
        super().__init__()
        self.desk_name = desk_name
        self._gateway = gateway
        self._history = history
        self._transcript = chat_transcript.ChatTranscript()
        self._views: dict[str, Any] = {}
        self._loading = True
        self._held_events: list[dict[str, Any]] = []
        self._desks_document: dict[str, Any] = {}
        self._connection = event_stream.CONNECTING
        self._tools_expanded = False
        self._last_escape = 0.0
        self._last_interrupt = 0.0
        self._last_exit_press = 0.0
        self._commands: list[dict[str, Any]] = []
        self._names = model_names.ModelNames()

    def compose(self):
        """Builds the screen.

        Yields:
            Widget: The status line, the transcript, the progress line, the command menu, the message box and the key hints.
        """
        yield widgets.Static('', id='status-line')
        with containers.Horizontal(id='chat-body'):
            yield containers.VerticalScroll(id='transcript')
        yield progress_line.ProgressLine()
        yield command_menu.CommandMenu()
        with containers.Vertical(id='composer-box'):
            yield composer_module.Composer(self._history)
        yield widgets.Static(
            '[dim]enter send · shift+enter new line · / commands · esc stop · alt+d desk · alt+p model · ctrl+o tools · ? keys[/dim]',
            id='key-hints',
        )

    def on_mount(self) -> None:
        """Loads the desk's chat and focuses the message box."""
        self.query_one(composer_module.Composer).focus()
        self._show_status()
        self.load_desk(self.desk_name)

    def take_event(self, event: dict[str, Any]) -> None:
        """Adds one live event to the chat, when it belongs to this desk.

        Args:
            event (dict[str, Any]): The event.
        """
        if event.get('desk') != self.desk_name:
            return
        if self._loading:
            self._held_events.append(event)
            return
        self._add_events([event])

    def take_desks(self, document: dict[str, Any]) -> None:
        """Updates the status line and placeholder from the desks' states.

        Args:
            document (dict[str, Any]): The answer of GET /api/desks.
        """
        self._desks_document = document
        self._show_status()

    def take_connection(self, state: str) -> None:
        """Shows the event stream's state, and reloads the chat after a reconnect.

        Args:
            state (str): "connecting", "live", "reconnecting" or "refused".
        """
        was_down = self._connection == event_stream.RECONNECTING
        self._connection = state
        self._show_status()
        if was_down and state == event_stream.LIVE:
            self.load_desk(self.desk_name)

    def desk(self) -> dict[str, Any] | None:
        """The summary of the desk this chat shows.

        Returns:
            dict[str, Any] | None: The summary, or None before the desks are known.
        """
        for desk in self._desks_document.get('desks', []):
            if desk.get('name') == self.desk_name:
                return desk
        return None

    @work(exclusive=True, group='load')
    async def load_desk(self, desk_name: str) -> None:
        """Clears the chat and fills it with the desk's journal of today.

        Args:
            desk_name (str): The desk.
        """
        self.desk_name = desk_name
        self.app.remember_desk(desk_name)
        self._loading = True
        self._held_events = []
        self._transcript = chat_transcript.ChatTranscript()
        self._views = {}
        transcript = self.query_one('#transcript', containers.VerticalScroll)
        await transcript.remove_children()
        self._show_status()
        self._load_commands(desk_name)
        try:
            journal = await self._gateway.desk_journal(desk_name)
        except gateway_client.GatewayError as error:
            await transcript.mount(
                widgets.Static(
                    Content.from_markup(
                        "[$error]Could not read today's journal: $message[/]",
                        message=error.message,
                    ),
                    classes='notice',
                )
            )
            journal = {
                'events': [],
            }
        events = list(journal.get('events', []))
        held = self._held_events
        self._held_events = []
        self._loading = False
        if not events and not held:
            await transcript.mount(
                widgets.Static(
                    Content.from_markup(
                        '[dim]Nothing today yet with $desk. Say hello, or try /status.[/dim]',
                        desk=desk_name,
                    ),
                    classes='notice',
                    id='empty-notice',
                )
            )
        self._add_events(events + held)
        transcript.anchor()

    @work(exclusive=True, group='commands')
    async def _load_commands(self, desk_name: str) -> None:
        """Fills the command menu with the terminal's and the desk's commands.

        Args:
            desk_name (str): The desk.
        """
        entries = keys_screen.TerminalCommandList().entries()
        try:
            answer = await self._gateway.desk_commands(desk_name)
        except gateway_client.GatewayError:
            answer = {
                'commands': [],
            }
        for entry in answer.get('commands', []):
            if entry['name'] in _TERMINAL_COMMANDS:
                continue
            entries.append(entry)
        self.query_one(command_menu.CommandMenu).set_entries(entries)

    def on_text_area_changed(self, event: widgets.TextArea.Changed) -> None:
        """Opens or narrows the command menu as the user types.

        Args:
            event (widgets.TextArea.Changed): The change.
        """
        menu = self.query_one(command_menu.CommandMenu)
        composer = self.query_one(composer_module.Composer)
        composer.menu_open = menu.filter(event.text_area.text)

    def on_composer_menu_moved(
        self, event: composer_module.Composer.MenuMoved
    ) -> None:
        """Moves the command menu's highlight.

        Args:
            event (composer_module.Composer.MenuMoved): The move.
        """
        self.query_one(command_menu.CommandMenu).move(event.step)

    def on_composer_menu_picked(
        self, event: composer_module.Composer.MenuPicked
    ) -> None:
        """Puts the highlighted command into the message box.

        Args:
            event (composer_module.Composer.MenuPicked): The pick.
        """
        del event
        self._complete_command()

    def on_composer_submitted(
        self, event: composer_module.Composer.Submitted
    ) -> None:
        """Sends the message, or completes the highlighted command first.

        Args:
            event (composer_module.Composer.Submitted): The submission.
        """
        menu = self.query_one(command_menu.CommandMenu)
        composer = self.query_one(composer_module.Composer)
        text = event.text.strip()
        if composer.menu_open:
            name = menu.highlighted_name()
            if name is not None and name != text:
                self._complete_command()
                return
        if not text:
            return
        self._history.add(text)
        composer.set_text('')
        menu.hide()
        composer.menu_open = False
        if self._run_terminal_command(text):
            return
        self.query_one('#transcript', containers.VerticalScroll).anchor()
        self._send(text)

    @work(group='send')
    async def _send(self, text: str) -> None:
        """Sends a message or desk command to the desk.

        Args:
            text (str): The message.
        """
        try:
            await self._gateway.send_message(self.desk_name, text)
        except gateway_client.GatewayError as error:
            self.notify(error.message, title='Not sent', severity='error')
            self.query_one(composer_module.Composer).set_text(text)

    def action_escape(self) -> None:
        """Closes the menu, stops the running turn, or clears the box on a second press."""
        menu = self.query_one(command_menu.CommandMenu)
        composer = self.query_one(composer_module.Composer)
        if composer.menu_open:
            menu.hide()
            composer.menu_open = False
            return
        if self._desk_is_busy():
            self._send('/stop')
            self.notify('Stopping the running turn.', timeout=3)
            return
        now = time.monotonic()
        if composer.text and now - self._last_escape < _DOUBLE_PRESS_SECONDS:
            self._history.add(composer.text)
            composer.set_text('')
            return
        self._last_escape = now
        if composer.text:
            self.notify('Press esc again to clear the message box.', timeout=2)

    def action_interrupt(self) -> None:
        """Clears the box, stops the running turn, or exits on a second press."""
        composer = self.query_one(composer_module.Composer)
        if composer.text:
            composer.set_text('')
            return
        if self._desk_is_busy():
            self._send('/stop')
            self.notify('Stopping the running turn.', timeout=3)
            return
        now = time.monotonic()
        if now - self._last_interrupt < _DOUBLE_PRESS_SECONDS:
            self.app.exit()
            return
        self._last_interrupt = now
        self.notify(
            'Press ctrl+c again to exit. The desks keep running.', timeout=2
        )

    def action_exit_when_empty(self) -> None:
        """Exits on a second press while the box is empty; otherwise deletes forward."""
        composer = self.query_one(composer_module.Composer)
        if composer.text:
            composer.action_delete_right()
            return
        now = time.monotonic()
        if now - self._last_exit_press < _DOUBLE_PRESS_SECONDS:
            self.app.exit()
            return
        self._last_exit_press = now
        self.notify('Press ctrl+d again to exit.', timeout=2)

    def action_pick_desk(self) -> None:
        """Opens the desk list."""
        desks = self._desks_document.get('desks', [])
        if not desks:
            self.notify('The desks are not known yet.', severity='warning')
            return
        self.app.push_screen(
            desk_picker.DeskPicker(desks, self.desk_name), self._switch_desk
        )

    def action_pick_model(self) -> None:
        """Opens the model list for this desk."""
        desk = self.desk()
        if desk is None or not desk.get('backends'):
            self.notify(
                'This desk has no models to choose from.', severity='warning'
            )
            return
        self.app.push_screen(model_picker.ModelPicker(desk), self._choose_model)

    def action_toggle_tools(self) -> None:
        """Opens or folds every tool call in the chat."""
        transcript = self.query_one('#transcript', containers.VerticalScroll)
        at_bottom = (
            transcript.max_scroll_y - transcript.scroll_y <= _BOTTOM_SLACK_LINES
        )
        self._tools_expanded = not self._tools_expanded
        for view in self._views.values():
            if isinstance(view, turn_view.TurnView):
                view.expand_tools(self._tools_expanded)
        if at_bottom:
            transcript.anchor()
            transcript.call_after_refresh(transcript.scroll_end, animate=False)

    def action_search_history(self) -> None:
        """Opens the search of earlier prompts."""
        self.app.push_screen(
            history_search.HistorySearch(self._history), self._use_prompt
        )

    def on_composer_keys_wanted(
        self, event: composer_module.Composer.KeysWanted
    ) -> None:
        """Shows the keys when ? is typed into the empty message box.

        Args:
            event (composer_module.Composer.KeysWanted): The request.
        """
        del event
        self.app.push_screen(keys_screen.KeysScreen())

    def _run_terminal_command(self, text: str) -> bool:
        """Runs one of the terminal program's own commands.

        Args:
            text (str): The message.

        Returns:
            bool: True when the message was a terminal command and has been handled.
        """
        words = text.split()
        name = words[0].lower()
        if name == '/desk':
            if len(words) == 1:
                self.action_pick_desk()
            else:
                self._switch_desk(words[1])
            return True
        if name == '/model' and len(words) == 1:
            self.action_pick_model()
            return True
        if name == '/theme':
            self.app.toggle_theme()
            return True
        if name == '/keys':
            self.app.push_screen(keys_screen.KeysScreen())
            return True
        if name in ('/exit', '/quit'):
            self.app.exit()
            return True
        return False

    def _switch_desk(self, desk_name: str | None) -> None:
        """Shows another desk's chat.

        Args:
            desk_name (str | None): The desk, or None to stay.
        """
        if desk_name is None or desk_name == self.desk_name:
            return
        known = []
        for desk in self._desks_document.get('desks', []):
            known.append(desk.get('name'))
        if known and desk_name not in known:
            self.notify(
                f'No desk named {desk_name}. The desks are {", ".join(known)}.',
                severity='error',
            )
            return
        self.load_desk(desk_name)

    @work(group='model')
    async def _choose_model(
        self, choice: model_picker.ModelChoice | None
    ) -> None:
        """Makes the desk try the chosen model first.

        Args:
            choice (model_picker.ModelChoice | None): The backend and model, (None, None) for Auto, or None to leave it.
        """
        if choice is None:
            return
        backend_name, model = choice
        try:
            await self._gateway.choose_model(
                self.desk_name, backend_name, model
            )
        except gateway_client.GatewayError as error:
            self.notify(
                error.message, title='Model not changed', severity='error'
            )
            return
        self.app.refresh_desks()

    def _use_prompt(self, prompt: str | None) -> None:
        """Puts a prompt found by the search into the message box.

        Args:
            prompt (str | None): The prompt, or None to leave the box as it is.
        """
        if prompt is not None:
            self.query_one(composer_module.Composer).set_text(prompt)

    def _complete_command(self) -> None:
        """Replaces the draft with the highlighted command and a space."""
        menu = self.query_one(command_menu.CommandMenu)
        name = menu.highlighted_name()
        if name is None:
            return
        composer = self.query_one(composer_module.Composer)
        composer.set_text(f'{name} ')
        menu.hide()
        composer.menu_open = False

    def _add_events(self, events: list[dict[str, Any]]) -> None:
        """Adds events to the transcript and updates the views they changed.

        Args:
            events (list[dict[str, Any]]): The events, oldest first.
        """
        transcript = self.query_one('#transcript', containers.VerticalScroll)
        at_bottom = (
            transcript.max_scroll_y - transcript.scroll_y <= _BOTTOM_SLACK_LINES
        )
        changed: dict[int, Any] = {}
        for event in events:
            item = self._transcript.add(event)
            if item is not None:
                changed[id(item)] = item
        new_views = []
        for item in changed.values():
            key = self._item_key(item)
            view = self._views.get(key)
            if view is not None:
                if isinstance(view, turn_view.TurnView):
                    view.show(item)
                continue
            if isinstance(item, chat_items.ChatTurn):
                view = turn_view.TurnView(item)
            else:
                view = event_step_view.EventStepView(item.event, with_time=True)
            self._views[key] = view
            new_views.append(view)
        if new_views:
            for notice in self.query('#empty-notice'):
                notice.remove()
            transcript.mount_all(new_views)
        self._follow_progress()
        if at_bottom:
            transcript.anchor()

    def _item_key(self, item: Any) -> str:
        """The key a transcript item's view is kept under.

        Args:
            item (Any): A turn or a loose event.

        Returns:
            str: The trigger id for a turn, or the event's key for a loose event.
        """
        if isinstance(item, chat_items.ChatTurn):
            return item.trigger_id
        return self._transcript.key(item.event)

    def _follow_progress(self) -> None:
        """Points the progress line at the running turn, or the newest queued one."""
        line = self.query_one(progress_line.ProgressLine)
        running = self._transcript.running_turn()
        if running is not None:
            line.follow(running)
            return
        for item in reversed(self._transcript.items):
            if (
                isinstance(item, chat_items.ChatTurn)
                and not item.started
                and not item.finished
                and item.source == 'user_message'
            ):
                line.follow(item)
                return
        line.follow(None)

    def _desk_is_busy(self) -> bool:
        """Says whether the desk is working on a turn.

        Returns:
            bool: True when the desk is not idle, or a turn of this chat is running.
        """
        if self._transcript.running_turn() is not None:
            return True
        desk = self.desk()
        return desk is not None and desk.get('state') not in (None, 'idle')

    def _show_status(self) -> None:
        """Redraws the status line and the message box's placeholder, while the screen's widgets exist."""
        status_lines = self.query('#status-line')
        composers = self.query(composer_module.Composer)
        if not status_lines or not composers:
            return
        desk = self.desk()
        mode = self._desks_document.get('mode', '')
        mode_markup = ''
        if mode == 'live':
            mode_markup = '[b $error]LIVE ORDERS[/]'
        elif mode:
            mode_markup = '[b $success]DRY RUN[/]'
        state = ''
        model = ''
        if desk is not None:
            state = str(desk.get('state', ''))
            if desk.get('paused'):
                state += ', paused'
            if desk.get('queued'):
                state += f', {desk["queued"]} waiting'
            model = self._model_text(desk)
        connection = _CONNECTION_WORDS.get(self._connection, self._connection)
        dot = '[$success]●[/]'
        if self._connection != event_stream.LIVE:
            dot = '[$warning]●[/]'
        status_lines.first(widgets.Static).update(
            Content.from_markup(
                f'{dot} $connection   [b]$desk[/b] [dim]$state[/dim]   {mode_markup}   [dim]$model[/dim]',
                connection=connection,
                desk=self.desk_name,
                state=state,
                model=model,
            )
        )
        composer = composers.first(composer_module.Composer)
        if self._desk_is_busy():
            composer.placeholder = f'{self.desk_name} is working; a message now goes to it at its next tool call'
        else:
            composer.placeholder = (
                f'Message {self.desk_name}…  (/ for commands, ? for keys)'
            )

    def _model_text(self, desk: dict[str, Any]) -> str:
        """The model the desk tries first, or answered with last.

        Args:
            desk (dict[str, Any]): The desk summary.

        Returns:
            str: Such as "Opus (claude)" or "Auto · last Opus (claude)".
        """
        backends = desk.get('backends') or []
        preferred = desk.get('preferred_model')
        for backend in backends:
            if backend.get('name') == preferred:
                label = self._names.label(
                    backend.get('active_model') or backend.get('model')
                )
                return f'{label} ({preferred})'
        last = desk.get('last_model')
        if not last:
            return 'Auto'
        for backend in backends:
            if backend.get('name') == last:
                label = self._names.label(
                    backend.get('active_model') or backend.get('model')
                )
                return f'Auto · last {label} ({last})'
        return f'Auto · last {last}'
