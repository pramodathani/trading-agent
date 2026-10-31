"""A dialog listing the traders, for switching the chat to another one.

It returns the chosen trader's name, or None when the user presses Escape.

Typical usage example:

  app.push_screen(TraderPicker(traders, 'general'), on_chosen)
"""

from typing import Any, ClassVar

from textual import binding
from textual import containers
from textual import screen
from textual import widgets
from textual.content import Content
from textual.widgets import option_list


class TraderPicker(screen.ModalScreen[str | None]):
    """The trader list."""

    BINDINGS: ClassVar[list[binding.BindingType]] = [
        binding.Binding('escape', 'cancel', 'Close'),
    ]

    def __init__(self, traders: list[dict[str, Any]], current: str):
        """Creates the dialog.

        Args:
            traders (list[dict[str, Any]]): The trader summaries from GET /api/traders.
            current (str): The trader the chat shows now.
        """
        super().__init__(classes='picker-screen')
        self._traders = traders
        self._current = current

    def compose(self):
        """Builds the dialog.

        Yields:
            Widget: The title and the list.
        """
        with containers.Vertical(classes='picker'):
            yield widgets.Static('[b]Switch trader[/b]', classes='picker-title')
            options = []
            for trader in self._traders:
                options.append(option_list.Option(self._label(trader)))
            yield widgets.OptionList(*options, id='trader-options')
            yield widgets.Static(
                '[dim]↑↓ to move · enter to choose · esc to close[/dim]',
                classes='picker-hint',
            )

    def on_mount(self) -> None:
        """Highlights the current trader."""
        options = self.query_one('#trader-options', widgets.OptionList)
        for index, trader in enumerate(self._traders):
            if trader['name'] == self._current:
                options.highlighted = index
        options.focus()

    def on_option_list_option_selected(
        self, event: widgets.OptionList.OptionSelected
    ) -> None:
        """Returns the chosen trader.

        Args:
            event (widgets.OptionList.OptionSelected): The choice.
        """
        self.dismiss(self._traders[event.option_index]['name'])

    def action_cancel(self) -> None:
        """Closes the dialog without a choice."""
        self.dismiss(None)

    def _label(self, trader: dict[str, Any]) -> Content:
        """One trader's line.

        Args:
            trader (dict[str, Any]): The trader summary.

        Returns:
            Content: The name, a tick for the current trader, its state and waiting triggers.
        """
        state = str(trader.get('state', ''))
        if trader.get('paused'):
            state += ', paused'
        if trader.get('queued'):
            state += f', {trader["queued"]} waiting'
        tick = ' '
        if trader['name'] == self._current:
            tick = '✓'
        return Content.from_markup(
            '$tick [b]$name[/b]  [dim]$state[/dim]',
            tick=tick,
            name=trader['name'],
            state=state,
        )
