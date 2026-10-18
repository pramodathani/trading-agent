"""The Sessions page: a desk's memory search, its sessions with their exchanges, its daily summaries and its notes.

It copies the web page's SessionsPage.tsx.

Typical usage example:

  app.push_screen(SessionsScreen('general'))
"""

from typing import Any, ClassVar

from textual import binding
from textual import containers
from textual import widgets
from textual import work
from textual.content import Content
from textual.widgets import option_list

from trading_agent.terminal import formatter
from trading_agent.terminal import gateway_client
from trading_agent.terminal.screens import page_screen


class SessionsScreen(page_screen.PageScreen):
    """The Sessions page."""

    TITLE_TEXT = 'Sessions'
    REFRESH_SECONDS = 30.0
    PER_DESK = True

    BINDINGS: ClassVar[list[binding.BindingType]] = [
        binding.Binding('d', 'next_desk', 'Next desk'),
        binding.Binding('slash', 'focus_search', 'Search memory'),
    ]

    def __init__(self, desk_name: str):
        """Creates the page.

        Args:
            desk_name (str): The desk the chat shows.
        """
        super().__init__(desk_name)
        self._sessions: list[dict[str, Any]] = []
        self._formatter = formatter.Formatter()
        self._detail_shown = False

    def compose_page(self):
        """Builds the search, the session list, the exchanges and the summaries and notes.

        Yields:
            Widget: The page's parts.
        """
        yield widgets.Input(
            placeholder="Search the desk's memory, then press enter (/ to focus)",
            id='sessions-search',
        )
        with containers.Horizontal(classes='page-columns'):
            with containers.Vertical(classes='page-left'):
                yield widgets.Static('[b]Sessions[/b]', classes='page-heading')
                yield widgets.OptionList(id='sessions-list')
            with containers.VerticalScroll(
                classes='page-right', id='sessions-right'
            ):
                yield widgets.Static('', id='sessions-shown')

    @work(exclusive=True, group='page')
    async def refresh_page(self) -> None:
        """Reads the desk's sessions, summaries and notes."""
        gateway = self.app.gateway
        try:
            sessions = await gateway.sessions(self.desk_name)
            summaries = await gateway.summaries(self.desk_name)
            notes = await gateway.notes(self.desk_name)
        except gateway_client.GatewayError as error:
            self.problem(error.message)
            return
        self._sessions = sessions.get('sessions') or []
        current = sessions.get('current')
        listing = self.query_one('#sessions-list', widgets.OptionList)
        highlighted = listing.highlighted
        listing.clear_options()
        for session in self._sessions:
            mark = ''
            if session.get('session_id') == current:
                mark = '  current'
            listing.add_option(
                option_list.Option(
                    Content.from_markup(
                        '$session [dim]$count exchanges$mark[/dim]',
                        session=str(session.get('session_id')),
                        count=str(session.get('exchanges', 0)),
                        mark=mark,
                    )
                )
            )
        if highlighted is not None and highlighted < len(self._sessions):
            listing.highlighted = highlighted
        elif self._sessions:
            listing.highlighted = 0
        if not self._detail_shown:
            self._show_summaries_and_notes(
                summaries.get('summaries') or [], notes.get('notes') or []
            )

    def action_next_desk(self) -> None:
        """Shows the next desk, starting again from its summaries and notes."""
        self._detail_shown = False
        super().action_next_desk()

    def action_focus_search(self) -> None:
        """Moves to the search box."""
        self.query_one('#sessions-search', widgets.Input).focus()

    def on_option_list_option_selected(
        self, event: widgets.OptionList.OptionSelected
    ) -> None:
        """Shows the chosen session's exchanges.

        Args:
            event (widgets.OptionList.OptionSelected): The choice.
        """
        event.stop()
        self._show_session(
            str(self._sessions[event.option_index].get('session_id'))
        )

    def on_input_submitted(self, event: widgets.Input.Submitted) -> None:
        """Searches the desk's memory.

        Args:
            event (widgets.Input.Submitted): The search words.
        """
        event.stop()
        if event.value.strip():
            self._search(event.value.strip())

    @work(exclusive=True, group='detail')
    async def _show_session(self, session_id: str) -> None:
        """Shows one session's exchanges.

        Args:
            session_id (str): The session.
        """
        try:
            session = await self.app.gateway.session(self.desk_name, session_id)
        except gateway_client.GatewayError as error:
            self.problem(error.message)
            return
        self._detail_shown = True
        parts = [
            Content.from_markup('[b]Session $id[/b]', id=session_id),
        ]
        for exchange in session.get('exchanges') or []:
            parts.append(
                Content.from_markup(
                    '\n[dim]$time · $backend[/dim]\n[b $accent]$question[/]\n$answer',
                    time=self._formatter.day_time(
                        str(exchange.get('finished_at', ''))
                    ),
                    backend=str(exchange.get('backend_name', '')),
                    question=str(exchange.get('trigger_text', ''))[:600],
                    answer=str(exchange.get('answer', ''))[:2000],
                )
            )
        self._show(Content('\n').join(parts))

    @work(exclusive=True, group='detail')
    async def _search(self, keywords: str) -> None:
        """Searches the desk's memory and shows the hits.

        Args:
            keywords (str): The words to look for.
        """
        try:
            answer = await self.app.gateway.search(self.desk_name, keywords)
        except gateway_client.GatewayError as error:
            self.problem(error.message)
            return
        self._detail_shown = True
        hits = answer.get('hits') or []
        heading = f'{len(hits)} hits for "{keywords}"'
        if not answer.get('matched_every_word'):
            heading += ', matched some of the words'
        parts = [
            Content.from_markup('[b]$heading[/b]', heading=heading),
        ]
        for hit in hits:
            parts.append(
                Content.from_markup(
                    '\n[dim]$day · $kind[/dim]\n$snippet',
                    day=str(hit.get('day', '')),
                    kind=str(hit.get('kind', '')),
                    snippet=str(hit.get('snippet', '')),
                )
            )
        self._show(Content('\n').join(parts))

    def _show_summaries_and_notes(
        self,
        summaries: list[dict[str, Any]],
        notes: list[dict[str, Any]],
    ) -> None:
        """Shows the daily summaries and the notes files.

        Args:
            summaries (list[dict[str, Any]]): The summaries, each with date and text.
            notes (list[dict[str, Any]]): The notes, each with file and text.
        """
        parts = [
            Content.from_markup(
                '[dim]Choose a session on the left, or search above.[/dim]\n\n[b]Daily summaries[/b]'
            ),
        ]
        for summary in summaries:
            parts.append(
                Content.from_markup(
                    '\n[b $accent]$date[/]\n$text',
                    date=str(summary.get('date', '')),
                    text=str(summary.get('text', '')),
                )
            )
        parts.append(Content.from_markup('\n[b]Notes[/b]'))
        for note in notes:
            parts.append(
                Content.from_markup(
                    '\n[b $accent]$file[/]\n$text',
                    file=str(note.get('file', '')),
                    text=str(note.get('text', '')),
                )
            )
        self._show(Content('\n').join(parts))

    def _show(self, content: Content) -> None:
        """Replaces the right-hand pane.

        Args:
            content (Content): What to show.
        """
        self.query_one('#sessions-shown', widgets.Static).update(content)
        self.query_one(
            '#sessions-right', containers.VerticalScroll
        ).scroll_home(animate=False)
