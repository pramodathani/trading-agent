"""The box where the user writes messages, with Claude Code's keys.

Enter sends. A ? typed into the empty box asks for the list of keys. File paths pasted by dragging files onto the terminal become attachments, Ctrl+V attaches a picture on the clipboard, and Backspace in the empty box removes the newest attachment. Shift+Enter, Alt+Enter, Ctrl+J, or a backslash typed just before Enter, starts a new line. Up on the first line and Down on the last line move through earlier prompts. While the command menu is open, Up, Down and Tab move through the menu and Enter picks from it.

Typical usage example:

  composer = Composer(PromptHistory(None))
  # The screen handles Composer.Submitted, MenuMoved and MenuPicked.
"""

from pathlib import Path

from textual import events
from textual import message
from textual import widgets

from trading_agent.terminal import attachable_files
from trading_agent.terminal import prompt_history as prompt_history_module

_NEW_LINE_KEYS = (
    'shift+enter',
    'alt+enter',
    'ctrl+j',
)


class Composer(widgets.TextArea):
    """The message box.

    Attributes:
        menu_open: Whether the command menu above the box is showing, set by the screen.
    """

    class Submitted(message.Message):
        """The user pressed Enter to send what is in the box."""

        def __init__(self, text: str):
            """Creates the message.

            Args:
                text (str): What the box held.
            """
            super().__init__()
            self.text = text

    class MenuMoved(message.Message):
        """The user moved the command menu's highlight."""

        def __init__(self, step: int):
            """Creates the message.

            Args:
                step (int): -1 for up, 1 for down.
            """
            super().__init__()
            self.step = step

    class MenuPicked(message.Message):
        """The user picked the highlighted command with Tab."""

    class KeysWanted(message.Message):
        """The user typed ? into the empty box, asking for the list of keys."""

    class FilesDropped(message.Message):
        """Files were dragged onto the terminal, which pasted their paths."""

        def __init__(self, paths: list[Path]):
            """Creates the message.

            Args:
                paths (list[Path]): The files.
            """
            super().__init__()
            self.paths = paths

    class PictureWanted(message.Message):
        """The user pressed Ctrl+V, which attaches a picture on the clipboard."""

    class EmptyBackspace(message.Message):
        """The user pressed Backspace in the empty box, which removes the newest attached file."""

    def __init__(
        self,
        history: prompt_history_module.PromptHistory,
        placeholder: str = '',
    ):
        """Creates the box.

        Args:
            history (prompt_history_module.PromptHistory): The earlier prompts, for Up and Down.
            placeholder (str): The hint shown while the box is empty.
        """
        super().__init__(
            '',
            soft_wrap=True,
            show_line_numbers=False,
            highlight_cursor_line=False,
            compact=True,
            placeholder=placeholder,
            id='composer',
        )
        self.menu_open = False
        self._history = history

    def set_text(self, text: str) -> None:
        """Replaces the box's text and puts the cursor at its end.

        Args:
            text (str): The new text.
        """
        self.text = text
        self.move_cursor(self.document.end)

    async def _on_key(self, event: events.Key) -> None:
        """Handles the keys that differ from a plain text area.

        Args:
            event (events.Key): The key press.
        """
        key = event.key
        if key == 'ctrl+v':
            self._stop(event)
            self.post_message(self.PictureWanted())
            return
        if key == 'backspace' and not self.text:
            self._stop(event)
            self.post_message(self.EmptyBackspace())
            return
        if key == 'question_mark' and not self.text:
            self._stop(event)
            self.post_message(self.KeysWanted())
            return
        if key in _NEW_LINE_KEYS:
            self._stop(event)
            self.insert('\n')
            return
        if key == 'enter':
            self._stop(event)
            if self._ends_with_backslash():
                self._replace_backslash()
                return
            self.post_message(self.Submitted(self.text))
            return
        if self.menu_open and key in ('up', 'down'):
            self._stop(event)
            step = 1
            if key == 'up':
                step = -1
            self.post_message(self.MenuMoved(step))
            return
        if self.menu_open and key == 'tab':
            self._stop(event)
            self.post_message(self.MenuPicked())
            return
        if key == 'up' and self.cursor_location[0] == 0:
            earlier = self._history.previous(self.text)
            if earlier is not None:
                self._stop(event)
                self.set_text(earlier)
            return
        last_row = self.document.line_count - 1
        if key == 'down' and self.cursor_location[0] == last_row:
            later = self._history.next()
            if later is not None:
                self._stop(event)
                self.set_text(later)
            return
        await super()._on_key(event)

    async def _on_paste(self, event: events.Paste) -> None:
        """Attaches pasted file paths, as a drag and drop gives them; pastes anything else as text.

        Args:
            event (events.Paste): The paste.
        """
        paths = attachable_files.AttachableFiles().from_paste(event.text)
        if paths:
            event.stop()
            event.prevent_default()
            self.post_message(self.FilesDropped(paths))
            return
        await super()._on_paste(event)

    def paste_text(self) -> None:
        """Pastes Textual's own clipboard, when Ctrl+V found no picture."""
        self.action_paste()

    def _ends_with_backslash(self) -> bool:
        """Says whether the character just before the cursor is a backslash.

        Returns:
            bool: True when it is.
        """
        row, column = self.cursor_location
        if column == 0:
            return False
        return self.document.get_line(row)[column - 1] == '\\'

    def _replace_backslash(self) -> None:
        """Turns the backslash before the cursor into a new line."""
        row, column = self.cursor_location
        self.replace('\n', (row, column - 1), (row, column))

    def _stop(self, event: events.Key) -> None:
        """Keeps a key from reaching the text area and the screen.

        Args:
            event (events.Key): The key press.
        """
        event.stop()
        event.prevent_default()
