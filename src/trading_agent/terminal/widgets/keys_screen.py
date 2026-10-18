"""A dialog listing the terminal program's keys and its own commands, opened with ? or /keys.

Typical usage example:

  app.push_screen(KeysScreen())
"""

from typing import ClassVar

from textual import binding
from textual import containers
from textual import screen
from textual import widgets
from textual.content import Content

_KEYS = (
    (
        'enter',
        'send the message, or pick the highlighted command',
    ),
    (
        'shift+enter, ctrl+j',
        'start a new line (alt+enter, or \\ then enter, also work)',
    ),
    (
        'up, down',
        'earlier prompts, from the first or last line',
    ),
    (
        'ctrl+r',
        'search earlier prompts',
    ),
    (
        '/',
        'open the command menu; tab or enter picks',
    ),
    (
        'esc',
        'stop the running turn; twice clears the message box',
    ),
    (
        'ctrl+c',
        'clear the message box, or stop the turn; twice to exit',
    ),
    (
        'ctrl+d',
        'exit, when the message box is empty (press twice)',
    ),
    (
        'alt+d',
        'switch desk',
    ),
    (
        'alt+p',
        'choose the model',
    ),
    (
        'ctrl+o',
        'open or fold every tool call',
    ),
    (
        'ctrl+p',
        'command palette: every screen and action',
    ),
    (
        'ctrl+t',
        'switch between the dark and light theme',
    ),
)
_COMMANDS = (
    (
        '/desk [name]',
        'switch desk',
    ),
    (
        '/model',
        'choose the model (with a name, the desk handles it)',
    ),
    (
        '/theme',
        'switch between the dark and light theme',
    ),
    (
        '/keys',
        'this list',
    ),
    (
        '/exit',
        'leave the terminal program; the desks keep running',
    ),
)


class KeysScreen(screen.ModalScreen[None]):
    """The list of keys and terminal commands."""

    BINDINGS: ClassVar[list[binding.BindingType]] = [
        binding.Binding('escape,q,question_mark', 'close', 'Close'),
    ]

    def __init__(self):
        """Creates the dialog."""
        super().__init__(classes='picker-screen')

    def compose(self):
        """Builds the dialog.

        Yields:
            Widget: The title, the keys, the terminal commands and the hint.
        """
        with containers.VerticalScroll(classes='picker keys'):
            yield widgets.Static('[b]Keys[/b]', classes='picker-title')
            yield widgets.Static(self._lines(_KEYS))
            yield widgets.Static(
                '[b]Terminal commands[/b]  [dim]every other /command goes to the desk; try /help[/dim]',
                classes='picker-title keys-section',
            )
            yield widgets.Static(self._lines(_COMMANDS))
            yield widgets.Static(
                '[dim]esc to close[/dim]', classes='picker-hint'
            )

    def _lines(self, rows: tuple[tuple[str, str], ...]) -> Content:
        """Lays out rows of a name and what it does in two columns.

        Args:
            rows (tuple[tuple[str, str], ...]): The rows.

        Returns:
            Content: One line per row, with the names padded to the longest one.
        """
        width = 0
        for name, _ in rows:
            width = max(width, len(name))
        lines = []
        for name, does in rows:
            lines.append(
                Content.from_markup(
                    '[b $accent]$name[/]  $does',
                    name=name.ljust(width),
                    does=does,
                )
            )
        return Content('\n').join(lines)

    def action_close(self) -> None:
        """Closes the dialog."""
        self.dismiss(None)


class TerminalCommandList:
    """The terminal program's own commands, for the command menu."""

    def entries(self) -> list[dict[str, str]]:
        """The commands as menu entries.

        Returns:
            list[dict[str, str]]: Each with name, usage and description.
        """
        entries = []
        for usage, description in _COMMANDS:
            entries.append(
                {
                    'name': usage.split()[0],
                    'usage': usage,
                    'description': description,
                }
            )
        return entries
