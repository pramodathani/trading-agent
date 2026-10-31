"""Remembers the terminal program's choices between runs: the trader, the theme, the side panel and its folded cards.

They are kept in ~/.local/state/trading-agent/terminal.json, beside the prompt history. A missing or unreadable file gives the defaults.

Typical usage example:

  settings = TerminalSettings.load()
  settings.trader = 'scalper'
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
        trader: The trader the chat opened on last, or None.
        theme: The theme's name.
        side_panel_open: Whether the right-hand panel is shown.
        collapsed_cards: The side panel cards that are folded, by short name.
        file: Where the choices are kept.
    """

    def __init__(self, file: Path):
        """Creates the defaults.

        Args:
            file (Path): Where the choices are kept.
        """
        self.trader: str | None = None
        self.theme = terminal_themes.TerminalThemes.DARK
        self.side_panel_open = True
        self.collapsed_cards: list[str] = []
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
        if isinstance(stored.get('trader'), str):
            settings.trader = stored['trader']
        if stored.get('theme') in (
            terminal_themes.TerminalThemes.DARK,
            terminal_themes.TerminalThemes.LIGHT,
        ):
            settings.theme = stored['theme']
        if isinstance(stored.get('side_panel_open'), bool):
            settings.side_panel_open = stored['side_panel_open']
        collapsed = stored.get('collapsed_cards')
        if isinstance(collapsed, list):
            for card_id in collapsed:
                if isinstance(card_id, str):
                    settings.collapsed_cards.append(card_id)
        return settings

    def save(self) -> None:
        """Writes the choices, ignoring a folder that cannot be written."""
        try:
            self.file.parent.mkdir(parents=True, exist_ok=True)
            self.file.write_text(
                json.dumps(
                    {
                        'trader': self.trader,
                        'theme': self.theme,
                        'side_panel_open': self.side_panel_open,
                        'collapsed_cards': self.collapsed_cards,
                    },
                    indent=2,
                ),
                encoding='utf-8',
            )
        except OSError:
            return
