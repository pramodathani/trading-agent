"""The chat with one trader: today's turns, the live progress line and the message box.

The screen reads today's journal of the trader when it opens, then takes live events from the application. Events that arrive while the journal is still loading are held and added afterwards; ChatTranscript drops the ones the journal already had.

The terminal program's own commands (/attach, /trader, /model with no name, /theme, /keys, /exit, and one per page such as /trading) are handled here. Files are attached with @path in a message, /attach, by dragging them onto the terminal, or with Ctrl+V for a picture on the clipboard; they upload at once and go with the next message. Every other message, including every other /command, goes to the trader, which answers commands such as /status itself.

Typical usage example:

  app.push_screen(ChatScreen(gateway, history, 'general'))
"""

import time
from pathlib import Path
from typing import Any, ClassVar

from textual import binding
from textual import containers
from textual import screen
from textual import widgets
from textual import work
from textual.content import Content

from trading_agent.terminal import attachable_files
from trading_agent.terminal import attachment_opener
from trading_agent.terminal import chat_items
from trading_agent.terminal import chat_transcript
from trading_agent.terminal import clipboard_picture
from trading_agent.terminal import event_stream
from trading_agent.terminal import gateway_client
from trading_agent.terminal import model_names
from trading_agent.terminal import prompt_history as prompt_history_module
from trading_agent.terminal import terminal_settings
from trading_agent.terminal.screens import page_catalogue
from trading_agent.terminal.widgets import command_menu
from trading_agent.terminal.widgets import composer as composer_module
from trading_agent.terminal.widgets import event_step_view
from trading_agent.terminal.widgets import history_search
from trading_agent.terminal.widgets import keys_screen
from trading_agent.terminal.widgets import model_picker
from trading_agent.terminal.widgets import pending_files
from trading_agent.terminal.widgets import progress_line
from trading_agent.terminal.widgets import request_dock
from trading_agent.terminal.widgets import side_panel
from trading_agent.terminal.widgets import trader_message_view
from trading_agent.terminal.widgets import trader_picker
from trading_agent.terminal.widgets import turn_view

_DOUBLE_PRESS_SECONDS = 1.5
_REQUESTS_REFRESH_SECONDS = 30.0
_REQUEST_KINDS = (
    'user_request',
    'user_response',
)
_BOTTOM_SLACK_LINES = 3
_CONNECTION_WORDS = {
    event_stream.CONNECTING: 'Connecting…',
    event_stream.LIVE: 'Live',
    event_stream.RECONNECTING: 'Reconnecting…',
    event_stream.REFUSED: 'Token refused',
}
_TERMINAL_COMMANDS = (
    '/attach',
    '/trader',
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
        binding.Binding('tab', 'focus_dock', 'Answer', show=False),
        binding.Binding('alt+d', 'pick_trader', 'Trader'),
        binding.Binding('alt+p', 'pick_model', 'Model'),
        binding.Binding('ctrl+o', 'toggle_tools', 'Tools'),
        binding.Binding('ctrl+b', 'toggle_side_panel', 'Panel'),
        binding.Binding('ctrl+r', 'search_history', 'History'),
        binding.Binding('ctrl+t', 'app.toggle_theme', 'Theme'),
    ]

    def __init__(
        self,
        gateway: gateway_client.GatewayClient,
        history: prompt_history_module.PromptHistory,
        trader_name: str,
        settings: terminal_settings.TerminalSettings,
        opener: attachment_opener.AttachmentOpener,
    ):
        """Creates the screen.

        Args:
            gateway (gateway_client.GatewayClient): The gateway's routes.
            history (prompt_history_module.PromptHistory): The earlier prompts.
            trader_name (str): The trader to open on.
            settings (terminal_settings.TerminalSettings): The remembered choices, such as whether the side panel is shown.
            opener (attachment_opener.AttachmentOpener): Downloads and opens the trader's files.
        """
        super().__init__()
        self.trader_name = trader_name
        self._gateway = gateway
        self._history = history
        self._settings = settings
        self._opener = opener
        self._transcript = chat_transcript.ChatTranscript()
        self._views: dict[str, Any] = {}
        self._loading = True
        self._held_events: list[dict[str, Any]] = []
        self._traders_document: dict[str, Any] = {}
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
            yield side_panel.SidePanel(
                self._gateway, self._settings, self._opener
            )
        yield progress_line.ProgressLine()
        yield command_menu.CommandMenu()
        yield request_dock.RequestDock(self._gateway)
        yield pending_files.PendingFiles(self._gateway)
        with containers.Vertical(id='composer-box'):
            yield composer_module.Composer(self._history)
        yield widgets.Static(
            '[dim]enter send · shift+enter new line · / commands · esc stop · alt+d trader · alt+p model · ctrl+o tools · ctrl+b panel · f2 pages · ? keys[/dim]',
            id='key-hints',
        )

    def on_mount(self) -> None:
        """Loads the trader's chat and focuses the message box."""
        self.query_one(composer_module.Composer).focus()
        self.query_one(
            side_panel.SidePanel
        ).display = self._settings.side_panel_open
        self._show_status()
        self.load_trader(self.trader_name)
        self.set_interval(_REQUESTS_REFRESH_SECONDS, self.refresh_requests)

    def take_event(self, event: dict[str, Any]) -> None:
        """Adds one live event to the chat, when it belongs to this trader.

        Args:
            event (dict[str, Any]): The event.
        """
        if event.get('trader') != self.trader_name:
            return
        if event.get('kind') in _REQUEST_KINDS:
            self.refresh_requests()
        if self._loading:
            self._held_events.append(event)
            return
        self._add_events([event])

    def take_traders(self, document: dict[str, Any]) -> None:
        """Updates the status line and placeholder from the traders' states.

        Args:
            document (dict[str, Any]): The answer of GET /api/traders.
        """
        self._traders_document = document
        self._show_status()
        for panel in self.query(side_panel.SidePanel):
            panel.take_trader(self.trader(), document.get('mode', ''))

    def take_connection(self, state: str) -> None:
        """Shows the event stream's state, and reloads the chat after a reconnect.

        Args:
            state (str): "connecting", "live", "reconnecting" or "refused".
        """
        was_down = self._connection == event_stream.RECONNECTING
        self._connection = state
        self._show_status()
        if was_down and state == event_stream.LIVE:
            self.load_trader(self.trader_name)

    def trader(self) -> dict[str, Any] | None:
        """The summary of the trader this chat shows.

        Returns:
            dict[str, Any] | None: The summary, or None before the traders are known.
        """
        for trader in self._traders_document.get('traders', []):
            if trader.get('name') == self.trader_name:
                return trader
        return None

    @work(exclusive=True, group='load')
    async def load_trader(self, trader_name: str) -> None:
        """Clears the chat and fills it with the trader's journal of today.

        Args:
            trader_name (str): The trader.
        """
        self.trader_name = trader_name
        self.app.remember_trader(trader_name)
        self._loading = True
        self._held_events = []
        self._transcript = chat_transcript.ChatTranscript()
        self._views = {}
        transcript = self.query_one('#transcript', containers.VerticalScroll)
        await transcript.remove_children()
        self._show_status()
        self._load_commands(trader_name)
        self.refresh_requests()
        panel = self.query_one(side_panel.SidePanel)
        panel.set_trader(trader_name)
        panel.take_trader(self.trader(), self._traders_document.get('mode', ''))
        try:
            journal = await self._gateway.trader_journal(trader_name)
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
                        '[dim]Nothing today yet with $trader. Say hello, or try /status.[/dim]',
                        trader=trader_name,
                    ),
                    classes='notice',
                    id='empty-notice',
                )
            )
        self._add_events(events + held)
        transcript.anchor()

    @work(exclusive=True, group='requests')
    async def refresh_requests(self) -> None:
        """Reads the pending requests and shows this trader's first one in the dock."""
        try:
            pending = await self._gateway.requests('pending')
        except gateway_client.GatewayError:
            return
        mine = []
        for request in pending:
            if request.get('trader') == self.trader_name:
                mine.append(request)
        docks = self.query(request_dock.RequestDock)
        if not docks:
            return
        dock = docks.first(request_dock.RequestDock)
        focus_was_in_dock = (
            self.focused is not None
            and dock in self.focused.ancestors_with_self
        )
        if not dock.show(mine):
            return
        if dock.shown_request_id() is not None:
            self.notify(
                'The trader is waiting for your answer above the message box. Press tab to answer.',
                timeout=6,
            )
        if focus_was_in_dock:
            self.query_one(composer_module.Composer).focus()

    def on_request_dock_answered(
        self, event: request_dock.RequestDock.Answered
    ) -> None:
        """Reads the requests again after one was answered.

        Args:
            event (request_dock.RequestDock.Answered): The notice.
        """
        del event
        self.refresh_requests()

    @work(exclusive=True, group='commands')
    async def _load_commands(self, trader_name: str) -> None:
        """Fills the command menu with the terminal's and the trader's commands.

        Args:
            trader_name (str): The trader.
        """
        entries = keys_screen.TerminalCommandList().entries()
        for page in page_catalogue.PageCatalogue().pages():
            entries.append(
                {
                    'name': page.command,
                    'usage': page.command,
                    'description': f'open the {page.title} page: {page.description}',
                }
            )
        try:
            answer = await self._gateway.trader_commands(trader_name)
        except gateway_client.GatewayError:
            answer = {
                'commands': [],
            }
        for entry in answer.get('commands', []):
            if entry['name'] in _TERMINAL_COMMANDS:
                continue
            if page_catalogue.PageCatalogue().find(entry['name']) is not None:
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
        text = event.text_area.text
        last_word = ''
        if text and not text[-1].isspace():
            last_word = text.split()[-1]
        if last_word.startswith('@'):
            suggestions = attachable_files.AttachableFiles().suggestions(
                last_word[1:]
            )
            composer.menu_open = menu.show_paths(suggestions)
            return
        composer.menu_open = menu.filter(text)

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
            if menu.showing_paths and name is not None:
                self._complete_command()
                return
            if name is not None and name != text:
                self._complete_command()
                return
        tray = self.query_one(pending_files.PendingFiles)
        if not text and not tray.has_files():
            return
        if text:
            self._history.add(text)
        composer.set_text('')
        menu.hide()
        composer.menu_open = False
        if text and self._run_terminal_command(text):
            return
        for word, path in attachable_files.AttachableFiles().mentioned(text):
            problem = tray.add(self.trader_name, path)
            if problem is not None:
                self.notify(problem, title='Not attached', severity='error')
                composer.set_text(text)
                return
            text = text.replace(word, '', 1).strip()
        self.query_one('#transcript', containers.VerticalScroll).anchor()
        self._send(text)

    @work(group='send')
    async def _send(self, text: str) -> None:
        """Sends a message or trader command to the trader, with the files in the tray once they have uploaded.

        Args:
            text (str): The message.
        """
        tray = self.query_one(pending_files.PendingFiles)
        attachment_ids: list[str] = []
        if tray.has_files() and text != '/stop':
            attachment_ids, problems = await tray.ready_ids()
            for problem in problems:
                self.notify(problem, title='Not attached', severity='error')
            if not attachment_ids and not text:
                return
        try:
            await self._gateway.send_message(
                self.trader_name, text, attachment_ids
            )
        except gateway_client.GatewayError as error:
            self.notify(error.message, title='Not sent', severity='error')
            self.query_one(composer_module.Composer).set_text(text)
            return
        if attachment_ids:
            tray.clear()

    def on_composer_files_dropped(
        self, event: composer_module.Composer.FilesDropped
    ) -> None:
        """Attaches files dragged onto the terminal.

        Args:
            event (composer_module.Composer.FilesDropped): The files.
        """
        self._attach_files(event.paths)

    def on_composer_empty_backspace(
        self, event: composer_module.Composer.EmptyBackspace
    ) -> None:
        """Removes the newest attached file.

        Args:
            event (composer_module.Composer.EmptyBackspace): The key press.
        """
        del event
        self.query_one(pending_files.PendingFiles).remove_newest()

    @work(group='clipboard', thread=True)
    def on_composer_picture_wanted(
        self, event: composer_module.Composer.PictureWanted
    ) -> None:
        """Attaches a picture on the clipboard, or pastes text when there is none.

        Args:
            event (composer_module.Composer.PictureWanted): The key press.
        """
        del event
        folder = self.app.opener.folder / 'clipboard'
        path = clipboard_picture.ClipboardPicture().save(folder)
        if path is None:
            self.app.call_from_thread(self._paste_text)
            return
        self.app.call_from_thread(self._attach_files, [path])

    def _paste_text(self) -> None:
        """Pastes text into the message box when Ctrl+V found no picture."""
        self.query_one(composer_module.Composer).paste_text()

    def _attach_files(self, paths: list[Path]) -> None:
        """Adds files to the tray of the next message.

        Args:
            paths (list[Path]): The files.
        """
        tray = self.query_one(pending_files.PendingFiles)
        for path in paths:
            problem = tray.add(self.trader_name, path)
            if problem is not None:
                self.notify(problem, title='Not attached', severity='error')

    def action_escape(self) -> None:
        """Closes the menu, stops the running turn, or clears the box on a second press."""
        menu = self.query_one(command_menu.CommandMenu)
        composer = self.query_one(composer_module.Composer)
        if composer.menu_open:
            menu.hide()
            composer.menu_open = False
            return
        if self._trader_is_busy():
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
        if self._trader_is_busy():
            self._send('/stop')
            self.notify('Stopping the running turn.', timeout=3)
            return
        now = time.monotonic()
        if now - self._last_interrupt < _DOUBLE_PRESS_SECONDS:
            self.app.exit()
            return
        self._last_interrupt = now
        self.notify(
            'Press ctrl+c again to exit. The traders keep running.', timeout=2
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

    def action_pick_trader(self) -> None:
        """Opens the trader list."""
        traders = self._traders_document.get('traders', [])
        if not traders:
            self.notify('The traders are not known yet.', severity='warning')
            return
        self.app.push_screen(
            trader_picker.TraderPicker(traders, self.trader_name),
            self._switch_trader,
        )

    def action_pick_model(self) -> None:
        """Opens the model list for this trader."""
        trader = self.trader()
        if trader is None or not trader.get('backends'):
            self.notify(
                'This trader has no models to choose from.', severity='warning'
            )
            return
        self.app.push_screen(
            model_picker.ModelPicker(trader), self._choose_model
        )

    def action_toggle_side_panel(self) -> None:
        """Shows or hides the side panel, and remembers the choice."""
        panel = self.query_one(side_panel.SidePanel)
        panel.display = not panel.display
        self._settings.side_panel_open = bool(panel.display)
        self._settings.save()

    def action_focus_dock(self) -> None:
        """Moves to the waiting request's card, or to the next widget when nothing waits."""
        dock = self.query_one(request_dock.RequestDock)
        if not dock.focus_card():
            self.focus_next()

    def on_request_dock_left(
        self, event: request_dock.RequestDock.Left
    ) -> None:
        """Goes back to the message box when the user leaves a card with Escape.

        Args:
            event (request_dock.RequestDock.Left): The notice.
        """
        del event
        self.query_one(composer_module.Composer).focus()

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
        if name == '/attach':
            path_text = text[len(words[0]) :].strip()
            if not path_text:
                self.notify(
                    'Say which file: /attach path/to/file', severity='warning'
                )
                return True
            self._attach_files([Path(path_text).expanduser()])
            return True
        if name == '/trader':
            if len(words) == 1:
                self.action_pick_trader()
            else:
                self._switch_trader(words[1])
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
        if len(words) > 1:
            return False
        return self.app.open_page(name)

    def show_trader(self, trader_name: str) -> None:
        """Shows another trader's chat, as the Traders page asks.

        Args:
            trader_name (str): The trader.
        """
        self._switch_trader(trader_name)

    def _switch_trader(self, trader_name: str | None) -> None:
        """Shows another trader's chat.

        Args:
            trader_name (str | None): The trader, or None to stay.
        """
        if trader_name is None or trader_name == self.trader_name:
            return
        known = []
        for trader in self._traders_document.get('traders', []):
            known.append(trader.get('name'))
        if known and trader_name not in known:
            self.notify(
                f'No trader named {trader_name}. The traders are {", ".join(known)}.',
                severity='error',
            )
            return
        self.load_trader(trader_name)

    @work(group='model')
    async def _choose_model(
        self, choice: model_picker.ModelChoice | None
    ) -> None:
        """Makes the trader try the chosen model first.

        Args:
            choice (model_picker.ModelChoice | None): The backend and model, (None, None) for Auto, or None to leave it.
        """
        if choice is None:
            return
        backend_name, model = choice
        try:
            await self._gateway.choose_model(
                self.trader_name, backend_name, model
            )
        except gateway_client.GatewayError as error:
            self.notify(
                error.message, title='Model not changed', severity='error'
            )
            return
        self.app.refresh_traders()

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
        if menu.showing_paths:
            text = composer.text
            last_word = text.split()[-1]
            ending = ' '
            if name.endswith('/'):
                ending = ''
            composer.set_text(
                f'{text[: len(text) - len(last_word)]}@{name}{ending}'
            )
            if name.endswith('/'):
                return
        else:
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
        for panel in self.query(side_panel.SidePanel):
            panel.take_events(events)
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
                view = turn_view.TurnView(self.trader_name, item)
            elif item.event.get('kind') == 'message':
                view = trader_message_view.TraderMessageView(
                    self.trader_name, item.event, with_time=True
                )
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

    def _trader_is_busy(self) -> bool:
        """Says whether the trader is working on a turn.

        Returns:
            bool: True when the trader is not idle, or a turn of this chat is running.
        """
        if self._transcript.running_turn() is not None:
            return True
        trader = self.trader()
        return trader is not None and trader.get('state') not in (None, 'idle')

    def _show_status(self) -> None:
        """Redraws the status line and the message box's placeholder, while the screen's widgets exist."""
        status_lines = self.query('#status-line')
        composers = self.query(composer_module.Composer)
        if not status_lines or not composers:
            return
        trader = self.trader()
        mode = self._traders_document.get('mode', '')
        mode_markup = ''
        if mode == 'live':
            mode_markup = '[b $error]LIVE ORDERS[/]'
        elif mode:
            mode_markup = '[b $success]DRY RUN[/]'
        state = ''
        model = ''
        if trader is not None:
            state = str(trader.get('state', ''))
            if trader.get('paused'):
                state += ', paused'
            if trader.get('queued'):
                state += f', {trader["queued"]} waiting'
            model = self._model_text(trader)
        connection = _CONNECTION_WORDS.get(self._connection, self._connection)
        dot = '[$success]●[/]'
        if self._connection != event_stream.LIVE:
            dot = '[$warning]●[/]'
        status_lines.first(widgets.Static).update(
            Content.from_markup(
                f'{dot} $connection   [b]$trader[/b] [dim]$state[/dim]   {mode_markup}   [dim]$model[/dim]',
                connection=connection,
                trader=self.trader_name,
                state=state,
                model=model,
            )
        )
        composer = composers.first(composer_module.Composer)
        if self._trader_is_busy():
            composer.placeholder = f'{self.trader_name} is working; a message now goes to it at its next tool call'
        else:
            composer.placeholder = (
                f'Message {self.trader_name}…  (/ for commands, ? for keys)'
            )

    def _model_text(self, trader: dict[str, Any]) -> str:
        """The model the trader tries first, or answered with last.

        Args:
            trader (dict[str, Any]): The trader summary.

        Returns:
            str: Such as "Opus (claude)" or "Auto · last Opus (claude)".
        """
        backends = trader.get('backends') or []
        preferred = trader.get('preferred_model')
        for backend in backends:
            if backend.get('name') == preferred:
                label = self._names.label(
                    backend.get('active_model') or backend.get('model')
                )
                return f'{label} ({preferred})'
        last = trader.get('last_model')
        if not last:
            return 'Auto'
        for backend in backends:
            if backend.get('name') == last:
                label = self._names.label(
                    backend.get('active_model') or backend.get('model')
                )
                return f'Auto · last {label} ({last})'
        return f'Auto · last {last}'
