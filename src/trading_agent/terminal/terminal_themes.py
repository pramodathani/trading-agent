"""The terminal program's dark and light themes, in the web page's colours.

Typical usage example:

  for theme in TerminalThemes().all():
      app.register_theme(theme)
  app.theme = TerminalThemes.DARK
"""

from textual import theme as theme_module


class TerminalThemes:
    """The two themes, coloured like the web page's tokens.css."""

    DARK = 'trading-agent-dark'
    LIGHT = 'trading-agent-light'

    def all(self) -> list[theme_module.Theme]:
        """Both themes.

        Returns:
            list[theme_module.Theme]: The dark theme, then the light theme.
        """
        return [
            self._dark(),
            self._light(),
        ]

    def other(self, name: str) -> str:
        """The theme to switch to from the current one.

        Args:
            name (str): The current theme's name.

        Returns:
            str: The light theme's name when the dark one is current, otherwise the dark theme's name.
        """
        if name == self.DARK:
            return self.LIGHT
        return self.DARK

    def _dark(self) -> theme_module.Theme:
        """The dark theme.

        Returns:
            theme_module.Theme: The theme.
        """
        return theme_module.Theme(
            name=self.DARK,
            primary='#d97757',
            secondary='#6da7ec',
            accent='#d97757',
            warning='#fab219',
            error='#e66767',
            success='#0ca30c',
            foreground='#f0efec',
            background='#151515',
            surface='#20201f',
            panel='#1b1b1a',
            dark=True,
            variables={
                'text-muted': '#898781',
                'text-secondary': '#c3c2b7',
                'border': '#3a3a38',
                'footer-key-foreground': '#d97757',
                'input-selection-background': '#d97757 30%',
            },
        )

    def _light(self) -> theme_module.Theme:
        """The light theme.

        Returns:
            theme_module.Theme: The theme.
        """
        return theme_module.Theme(
            name=self.LIGHT,
            primary='#c6613f',
            secondary='#2a78d6',
            accent='#c6613f',
            warning='#a66a00',
            error='#d03b3b',
            success='#009300',
            foreground='#0b0b0b',
            background='#fcfcfb',
            surface='#ffffff',
            panel='#f3f2ef',
            dark=False,
            variables={
                'text-muted': '#7b7974',
                'text-secondary': '#52514e',
                'border': '#dcdbd7',
                'footer-key-foreground': '#c6613f',
                'input-selection-background': '#c6613f 25%',
            },
        )
