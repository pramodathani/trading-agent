"""The list of pages, opened with F2, standing in for the web page's sidebar.

It returns the chosen page's command, or None when the user presses Escape.

Typical usage example:

  app.push_screen(PagePicker(), on_chosen)
"""

from typing import ClassVar

from textual import binding
from textual import containers
from textual import screen
from textual import widgets
from textual.content import Content
from textual.widgets import option_list

from trading_agent.terminal.screens import page_catalogue


class PagePicker(screen.ModalScreen[str | None]):
    """The page list."""

    BINDINGS: ClassVar[list[binding.BindingType]] = [
        binding.Binding('escape', 'cancel', 'Close'),
    ]

    def __init__(self):
        """Creates the list."""
        super().__init__(classes='picker-screen')
        self._pages = page_catalogue.PageCatalogue().pages()

    def compose(self):
        """Builds the list.

        Yields:
            Widget: The title, the pages and the hint.
        """
        with containers.Vertical(classes='picker'):
            yield widgets.Static('[b]Go to[/b]', classes='picker-title')
            options = []
            for page in self._pages:
                options.append(
                    option_list.Option(
                        Content.from_markup(
                            '[b]$title[/b]  [dim]$command · $description[/dim]',
                            title=page.title,
                            command=page.command,
                            description=page.description,
                        )
                    )
                )
            yield widgets.OptionList(*options, id='page-options')
            yield widgets.Static(
                '[dim]↑↓ to move · enter to open · esc to close[/dim]',
                classes='picker-hint',
            )

    def on_mount(self) -> None:
        """Focuses the list."""
        self.query_one('#page-options', widgets.OptionList).focus()

    def on_option_list_option_selected(
        self, event: widgets.OptionList.OptionSelected
    ) -> None:
        """Returns the chosen page's command.

        Args:
            event (widgets.OptionList.OptionSelected): The choice.
        """
        self.dismiss(self._pages[event.option_index].command)

    def action_cancel(self) -> None:
        """Closes the list without a choice."""
        self.dismiss(None)
