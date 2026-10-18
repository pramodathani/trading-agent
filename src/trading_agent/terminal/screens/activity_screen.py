"""The Activity page: every event of today, from every desk, newest first, with live events added as they arrive.

It copies the web page's ActivityPage.tsx: a filter by desk, a text search, and routine events hidden unless asked for. Up to 600 rows are shown.

Typical usage example:

  app.push_screen(ActivityScreen('general'))
"""

from typing import Any, ClassVar

from textual import binding
from textual import widgets
from textual import work
from textual.content import Content

from trading_agent.terminal import event_describer
from trading_agent.terminal import formatter
from trading_agent.terminal import gateway_client
from trading_agent.terminal.screens import page_screen

_JOURNAL_LIMIT = 1000
_MOST_ROWS = 600
_ALL_DESKS = 'all desks'


class ActivityScreen(page_screen.PageScreen):
    """The Activity page."""

    TITLE_TEXT = 'Activity'

    BINDINGS: ClassVar[list[binding.BindingType]] = [
        binding.Binding('d', 'next_filter_desk', 'Desk filter'),
        binding.Binding('o', 'toggle_routine', 'Routine events'),
        binding.Binding('slash', 'focus_search', 'Search'),
    ]

    def __init__(self, desk_name: str):
        """Creates the page.

        Args:
            desk_name (str): The desk the chat shows.
        """
        super().__init__(desk_name)
        self._events: list[dict[str, Any]] = []
        self._keys: set[str] = set()
        self._filter_desk = _ALL_DESKS
        self._show_routine = False
        self._describer = event_describer.EventDescriber()
        self._formatter = formatter.Formatter()

    def compose_page(self):
        """Builds the filter line, the search box and the feed.

        Yields:
            Widget: The filters, the search box and the table.
        """
        yield widgets.Static('', id='activity-filters', classes='page-summary')
        yield widgets.Input(
            placeholder='Search (/ to focus)', id='activity-search'
        )
        yield widgets.DataTable(id='activity', cursor_type='row')

    def on_mount(self) -> None:
        """Sets up the table, then reads the journals."""
        table = self.table('activity')
        table.add_column('Time', width=8)
        table.add_column('Desk', width=10)
        table.add_column('What', width=46)
        table.add_column('Detail')
        self._show_filters()
        super().on_mount()

    @work(exclusive=True, group='page')
    async def refresh_page(self) -> None:
        """Reads today's journal of every desk and the events of no desk."""
        gateway = self.app.gateway
        events = []
        try:
            for desk in self.app.desks_document.get('desks', []):
                journal = await gateway.desk_journal(
                    desk.get('name'), _JOURNAL_LIMIT
                )
                events.extend(journal.get('events', []))
            journal = await gateway.journal(_JOURNAL_LIMIT)
            events.extend(journal.get('events', []))
        except gateway_client.GatewayError as error:
            self.problem(error.message)
            return
        self._events = []
        self._keys = set()
        for event in events:
            self._remember(event)
        self._show_rows()

    def take_event(self, event: dict[str, Any]) -> None:
        """Adds a live event to the feed.

        Args:
            event (dict[str, Any]): The event.
        """
        if event.get('kind') == 'text_delta':
            return
        if self._remember(event):
            self._show_rows()

    def on_input_changed(self, event: widgets.Input.Changed) -> None:
        """Filters the feed by the search text.

        Args:
            event (widgets.Input.Changed): The new search text.
        """
        event.stop()
        self._show_rows()

    def action_next_filter_desk(self) -> None:
        """Cycles the desk filter through all desks and each desk."""
        choices = [
            _ALL_DESKS,
        ]
        for desk in self.app.desks_document.get('desks', []):
            choices.append(desk.get('name'))
        index = 0
        if self._filter_desk in choices:
            index = (choices.index(self._filter_desk) + 1) % len(choices)
        self._filter_desk = choices[index]
        self._show_filters()
        self._show_rows()

    def action_toggle_routine(self) -> None:
        """Shows or hides routine events, such as turn starts and model usage."""
        self._show_routine = not self._show_routine
        self._show_filters()
        self._show_rows()

    def action_focus_search(self) -> None:
        """Moves to the search box."""
        self.query_one('#activity-search', widgets.Input).focus()

    def _remember(self, event: dict[str, Any]) -> bool:
        """Keeps an event unless it was already kept.

        Args:
            event (dict[str, Any]): The event.

        Returns:
            bool: True when it was new.
        """
        payload = event.get('payload') or {}
        key = f'{event.get("created_at")}|{event.get("kind")}|{event.get("desk")}|{payload.get("trigger_id")}|{payload.get("call_id")}'
        if key in self._keys:
            return False
        self._keys.add(key)
        self._events.append(event)
        return True

    def _show_filters(self) -> None:
        """Redraws the filter line."""
        routine = 'hidden'
        if self._show_routine:
            routine = 'shown'
        self.query_one('#activity-filters', widgets.Static).update(
            Content.from_markup(
                'Desk [b]$desk[/b] [dim](d)[/dim]   Routine events [b]$routine[/b] [dim](o)[/dim]',
                desk=self._filter_desk,
                routine=routine,
            )
        )

    def _show_rows(self) -> None:
        """Redraws the feed, newest first."""
        words = self.query_one('#activity-search', widgets.Input).value.lower()
        ordered = sorted(
            self._events, key=lambda event: str(event.get('created_at', ''))
        )
        table = self.table('activity')
        table.clear()
        shown = 0
        for event in reversed(ordered):
            if shown >= _MOST_ROWS:
                break
            if event.get('kind') == 'text_delta':
                continue
            desk = event.get('desk') or ''
            if self._filter_desk != _ALL_DESKS and desk != self._filter_desk:
                continue
            description = self._describer.describe(event)
            if description.tone == 'quiet' and not self._show_routine:
                continue
            detail = description.detail.replace('\n', ' ')
            if words and words not in f'{description.title} {detail}'.lower():
                continue
            colour = {
                'good': '$success',
                'warning': '$warning',
                'bad': '$error',
                'quiet': '$text-muted',
            }.get(description.tone, '$foreground')
            table.add_row(
                self._formatter.time(str(event.get('created_at', ''))),
                desk or '—',
                Content.from_markup(
                    f'[{colour}]$title[/]', title=description.title
                ),
                detail[:120],
            )
            shown += 1
