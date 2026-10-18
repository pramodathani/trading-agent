"""A dialog listing the desks, for switching the chat to another one.

It returns the chosen desk's name, or None when the user presses Escape.

Typical usage example:

  app.push_screen(DeskPicker(desks, 'general'), on_chosen)
"""

from typing import Any, ClassVar

from textual import binding
from textual import containers
from textual import screen
from textual import widgets
from textual.content import Content
from textual.widgets import option_list


class DeskPicker(screen.ModalScreen[str | None]):
    """The desk list."""

    BINDINGS: ClassVar[list[binding.BindingType]] = [
        binding.Binding('escape', 'cancel', 'Close'),
    ]

    def __init__(self, desks: list[dict[str, Any]], current: str):
        """Creates the dialog.

        Args:
            desks (list[dict[str, Any]]): The desk summaries from GET /api/desks.
            current (str): The desk the chat shows now.
        """
        super().__init__(classes='picker-screen')
        self._desks = desks
        self._current = current

    def compose(self):
        """Builds the dialog.

        Yields:
            Widget: The title and the list.
        """
        with containers.Vertical(classes='picker'):
            yield widgets.Static('[b]Switch desk[/b]', classes='picker-title')
            options = []
            for desk in self._desks:
                options.append(option_list.Option(self._label(desk)))
            yield widgets.OptionList(*options, id='desk-options')
            yield widgets.Static(
                '[dim]↑↓ to move · enter to choose · esc to close[/dim]',
                classes='picker-hint',
            )

    def on_mount(self) -> None:
        """Highlights the current desk."""
        options = self.query_one('#desk-options', widgets.OptionList)
        for index, desk in enumerate(self._desks):
            if desk['name'] == self._current:
                options.highlighted = index
        options.focus()

    def on_option_list_option_selected(
        self, event: widgets.OptionList.OptionSelected
    ) -> None:
        """Returns the chosen desk.

        Args:
            event (widgets.OptionList.OptionSelected): The choice.
        """
        self.dismiss(self._desks[event.option_index]['name'])

    def action_cancel(self) -> None:
        """Closes the dialog without a choice."""
        self.dismiss(None)

    def _label(self, desk: dict[str, Any]) -> Content:
        """One desk's line.

        Args:
            desk (dict[str, Any]): The desk summary.

        Returns:
            Content: The name, a tick for the current desk, its state and waiting triggers.
        """
        state = str(desk.get('state', ''))
        if desk.get('paused'):
            state += ', paused'
        if desk.get('queued'):
            state += f', {desk["queued"]} waiting'
        tick = ' '
        if desk['name'] == self._current:
            tick = '✓'
        return Content.from_markup(
            '$tick [b]$name[/b]  [dim]$state[/dim]',
            tick=tick,
            name=desk['name'],
            state=state,
        )
