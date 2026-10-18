"""Remembers the terminal program's choices between runs: the desk, the theme and the side panel.

They are kept in ~/.local/state/trading-agent/terminal.json, beside the prompt history. A missing or unreadable file gives the defaults.

Typical usage example:

  settings = TerminalSettings.load()
  settings.desk = 'scalper'
  settings.save()
"""

import json
import os
from pathlib import Path
from typing import Self

from trading_agent.terminal import terminal_themes


class TerminalSettings:
    """The remembered choices.

    Attributes:
        desk: The desk the chat opened on last, or None.
        theme: The theme's name.
        side_panel_open: Whether the right-hand panel is shown.
        file: Where the choices are kept.
    """

    def __init__(self, file: Path):
        """Creates the defaults.

        Args:
            file (Path): Where the choices are kept.
        """
        self.desk: str | None = None
        self.theme = terminal_themes.TerminalThemes.DARK
        self.side_panel_open = True
        self.file = file

    @classmethod
    def state_directory(cls) -> Path:
        """The folder for the terminal program's state.

        Returns:
            Path: $XDG_STATE_HOME/trading-agent, or ~/.local/state/trading-agent.
        """
        base = os.environ.get('XDG_STATE_HOME')
        if base:
            return Path(base) / 'trading-agent'
        return Path.home() / '.local' / 'state' / 'trading-agent'

    @classmethod
    def load(cls, file: Path | None = None) -> Self:
        """Reads the remembered choices.

        Args:
            file (Path | None): The file, or None for terminal.json in the state folder.

        Returns:
            TerminalSettings: The choices, or the defaults when the file is missing or unreadable.
        """
        if file is None:
            file = cls.state_directory() / 'terminal.json'
        settings = cls(file)
        try:
            stored = json.loads(file.read_text(encoding='utf-8'))
        except OSError, ValueError:
            return settings
        if not isinstance(stored, dict):
            return settings
        if isinstance(stored.get('desk'), str):
            settings.desk = stored['desk']
        if stored.get('theme') in (
            terminal_themes.TerminalThemes.DARK,
            terminal_themes.TerminalThemes.LIGHT,
        ):
            settings.theme = stored['theme']
        if isinstance(stored.get('side_panel_open'), bool):
            settings.side_panel_open = stored['side_panel_open']
        return settings

    def save(self) -> None:
        """Writes the choices, ignoring a folder that cannot be written."""
        try:
            self.file.parent.mkdir(parents=True, exist_ok=True)
            self.file.write_text(
                json.dumps(
                    {
                        'desk': self.desk,
                        'theme': self.theme,
                        'side_panel_open': self.side_panel_open,
                    },
                    indent=2,
                ),
                encoding='utf-8',
            )
        except OSError:
            return
