"""The menu that opens above the message box when the user types a slash, as in Claude Code.

It lists the terminal program's own commands, then the desk's commands and skills, keeping those whose names start with what was typed. Each name appears once, with the usage and description of its first entry.

Typical usage example:

  menu = CommandMenu()
  menu.set_entries(entries)
  menu.filter('/st')
  menu.highlighted_name()  # '/status'
"""

from typing import Any

from textual import widgets
from textual.content import Content
from textual.widgets import option_list

_MOST_SHOWN = 8


class CommandMenu(widgets.OptionList):
    """The command menu; hidden while nothing matches."""

    def __init__(self):
        """Creates the menu, hidden and empty."""
        super().__init__(id='command-menu')
        self._entries: list[dict[str, Any]] = []
        self._shown: list[dict[str, Any]] = []
        self.can_focus = False

    def on_mount(self) -> None:
        """Hides the menu until something matches."""
        self.display = False

    def set_entries(self, entries: list[dict[str, Any]]) -> None:
        """Replaces the commands the menu offers.

        Args:
            entries (list[dict[str, Any]]): The entries, each with name, usage and description, in the order to show them.
        """
        self._entries = []
        seen = set()
        for entry in entries:
            if entry['name'] in seen:
                continue
            seen.add(entry['name'])
            self._entries.append(entry)

    def filter(self, draft: str) -> bool:
        """Shows the commands whose names start with the draft.

        Args:
            draft (str): What is in the message box.

        Returns:
            bool: True when the menu is showing.
        """
        self._shown = []
        if draft.startswith('/') and ' ' not in draft and '\n' not in draft:
            for entry in self._entries:
                if entry['name'].startswith(draft.lower()):
                    self._shown.append(entry)
        self.clear_options()
        for entry in self._shown:
            self.add_option(
                option_list.Option(
                    Content.from_markup(
                        '[b]$usage[/b]  [dim]$description[/dim]',
                        usage=entry['usage'],
                        description=entry['description'],
                    )
                )
            )
        self.display = bool(self._shown)
        self.styles.height = min(len(self._shown), _MOST_SHOWN) + 2
        if self._shown:
            self.highlighted = 0
        return bool(self._shown)

    def move(self, step: int) -> None:
        """Moves the highlight, wrapping at the ends.

        Args:
            step (int): -1 for up, 1 for down.
        """
        if not self._shown:
            return
        current = self.highlighted or 0
        self.highlighted = (current + step) % len(self._shown)

    def highlighted_name(self) -> str | None:
        """The highlighted command's name.

        Returns:
            str | None: Such as "/status", or None when the menu is empty.
        """
        if not self._shown or self.highlighted is None:
            return None
        return self._shown[self.highlighted]['name']

    def hide(self) -> None:
        """Hides the menu."""
        self._shown = []
        self.display = False
