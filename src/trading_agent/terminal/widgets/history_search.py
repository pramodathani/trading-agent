"""A dialog for finding an earlier prompt, opened with Ctrl+R as in Claude Code.

It returns the chosen prompt, or None when the user presses Escape.

Typical usage example:

  app.push_screen(HistorySearch(history), on_chosen)
"""

from typing import ClassVar

from textual import binding
from textual import containers
from textual import events
from textual import screen
from textual import widgets
from textual.content import Content
from textual.widgets import option_list

from trading_agent.terminal import prompt_history as prompt_history_module

_MOST_SHOWN = 50
_MOST_LINE_CHARACTERS = 120


class HistorySearch(screen.ModalScreen[str | None]):
    """The search box and its matches."""

    BINDINGS: ClassVar[list[binding.BindingType]] = [
        binding.Binding('escape', 'cancel', 'Close'),
    ]

    def __init__(self, history: prompt_history_module.PromptHistory):
        """Creates the dialog.

        Args:
            history (prompt_history_module.PromptHistory): The earlier prompts.
        """
        super().__init__(classes='picker-screen')
        self._history = history
        self._matches: list[str] = []

    def compose(self):
        """Builds the dialog.

        Yields:
            Widget: The title, the search box, the matches and the hint.
        """
        with containers.Vertical(classes='picker'):
            yield widgets.Static(
                '[b]Search earlier prompts[/b]', classes='picker-title'
            )
            yield widgets.Input(placeholder='words to look for', id='search')
            yield widgets.OptionList(id='matches')
            yield widgets.Static(
                '[dim]type to search · ↑↓ to move · enter to use · esc to close[/dim]',
                classes='picker-hint',
            )

    def on_mount(self) -> None:
        """Lists the newest prompts."""
        self._show('')
        self.query_one('#search', widgets.Input).focus()

    def on_input_changed(self, event: widgets.Input.Changed) -> None:
        """Lists the prompts that match the search.

        Args:
            event (widgets.Input.Changed): The new search text.
        """
        self._show(event.value)

    def on_key(self, event: events.Key) -> None:
        """Moves through the matches while the search box has the focus.

        Args:
            event (events.Key): The key press.
        """
        matches = self.query_one('#matches', widgets.OptionList)
        if event.key in ('up', 'down') and self._matches:
            event.stop()
            current = matches.highlighted or 0
            step = 1
            if event.key == 'up':
                step = -1
            matches.highlighted = (current + step) % len(self._matches)

    def on_input_submitted(self, event: widgets.Input.Submitted) -> None:
        """Uses the highlighted prompt.

        Args:
            event (widgets.Input.Submitted): The submission.
        """
        matches = self.query_one('#matches', widgets.OptionList)
        if not self._matches or matches.highlighted is None:
            self.dismiss(None)
            return
        self.dismiss(self._matches[matches.highlighted])

    def on_option_list_option_selected(
        self, event: widgets.OptionList.OptionSelected
    ) -> None:
        """Uses a clicked prompt.

        Args:
            event (widgets.OptionList.OptionSelected): The choice.
        """
        self.dismiss(self._matches[event.option_index])

    def action_cancel(self) -> None:
        """Closes the dialog without a choice."""
        self.dismiss(None)

    def _show(self, words: str) -> None:
        """Lists the matching prompts.

        Args:
            words (str): The search text.
        """
        self._matches = self._history.search(words)[:_MOST_SHOWN]
        matches = self.query_one('#matches', widgets.OptionList)
        matches.clear_options()
        for prompt in self._matches:
            line = prompt.replace('\n', ' ⏎ ')
            if len(line) > _MOST_LINE_CHARACTERS:
                line = line[: _MOST_LINE_CHARACTERS - 1] + '…'
            matches.add_option(option_list.Option(Content(line)))
        if self._matches:
            matches.highlighted = 0
