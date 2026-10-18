"""The shared frame of the terminal program's pages, such as Trading or Schedule: a title line, Escape to go back to the chat, and timed refreshes.

Each page is its own subclass, in its own file, with its own content. This base holds only what every page does the same way.

Typical usage example:

  class SkillsScreen(PageScreen):
      TITLE_TEXT = 'Skills'
      ...
"""

from typing import Any, ClassVar

from textual import binding
from textual import screen
from textual import widgets
from textual.content import Content


class PageScreen(screen.Screen[None]):
    """A page of the terminal program."""

    TITLE_TEXT = ''
    REFRESH_SECONDS = 0.0
    PER_DESK = False

    BINDINGS: ClassVar[list[binding.BindingType]] = [
        binding.Binding('escape', 'back', 'Back to the chat'),
        binding.Binding('r', 'refresh_page', 'Refresh'),
    ]

    def __init__(self, desk_name: str):
        """Creates the page.

        Args:
            desk_name (str): The desk the chat shows, which a desk's page starts on.
        """
        super().__init__(classes='page')
        self.desk_name = desk_name

    def compose(self):
        """Builds the frame around the page's own content.

        Yields:
            Widget: The title line, the content and the key footer.
        """
        yield widgets.Static('', id='page-title')
        yield from self.compose_page()
        yield widgets.Footer()

    def compose_page(self):
        """Builds the page's own content; each page overrides it.

        Yields:
            Widget: Nothing in the base.
        """
        yield from ()

    def on_mount(self) -> None:
        """Shows the title, focuses the first table or list, reads the page's data, and starts the timer."""
        self.show_title()
        self.call_after_refresh(self._focus_first_list)
        self.refresh_page()
        if self.REFRESH_SECONDS > 0:
            self.set_interval(self.REFRESH_SECONDS, self.refresh_page)

    def _focus_first_list(self) -> None:
        """Puts the focus on the page's first table or list, so its letter keys work rather than typing into a box."""
        for candidate in self.query('DataTable, OptionList'):
            candidate.focus()
            return

    def refresh_page(self) -> None:
        """Reads the page's data again; each page overrides it."""

    def take_event(self, event: dict[str, Any]) -> None:
        """Takes a live event; pages that follow events override it.

        Args:
            event (dict[str, Any]): The event.
        """
        del event

    def action_back(self) -> None:
        """Goes back to the chat."""
        self.app.pop_screen()

    def action_refresh_page(self) -> None:
        """Reads the page's data again now."""
        self.refresh_page()

    def action_next_desk(self) -> None:
        """Shows the next desk, on pages that show one desk."""
        names = []
        for desk in self.app.desks_document.get('desks', []):
            names.append(desk.get('name'))
        if not names:
            return
        index = 0
        if self.desk_name in names:
            index = (names.index(self.desk_name) + 1) % len(names)
        self.desk_name = names[index]
        self.show_title()
        self.refresh_page()

    def show_title(self) -> None:
        """Redraws the title line."""
        desk_part = ''
        if self.PER_DESK:
            desk_part = f'  ·  desk {self.desk_name} (d for the next desk)'
        self.query_one('#page-title', widgets.Static).update(
            Content.from_markup(
                '[b]$title[/b][dim]$desk  ·  esc back to the chat  ·  r refresh[/dim]',
                title=self.TITLE_TEXT,
                desk=desk_part,
            )
        )

    def problem(self, text: str) -> None:
        """Shows a problem reading or changing the page's data.

        Args:
            text (str): The problem.
        """
        self.notify(text, title=self.TITLE_TEXT, severity='error')

    def table(self, table_id: str) -> widgets.DataTable:
        """One of the page's tables.

        Args:
            table_id (str): The table's id, without the "#".

        Returns:
            widgets.DataTable: The table.
        """
        return self.query_one(f'#{table_id}', widgets.DataTable)

    def selected_key(self, table_id: str) -> str | None:
        """The key of a table's highlighted row.

        Args:
            table_id (str): The table's id.

        Returns:
            str | None: The row's key, or None when the table is empty.
        """
        table = self.table(table_id)
        if table.row_count == 0:
            return None
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        return row_key.value
