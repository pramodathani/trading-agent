"""A unified diff with added lines in green, removed lines in red and hunk headers dimmed, as the web page's DiffView.tsx shows it.

Typical usage example:

  view = DiffView()
  view.show(proposal['difference'])
"""

from textual import widgets
from textual.content import Content

_FILE_MARKERS = (
    '+++',
    '---',
)


class DiffView(widgets.Static):
    """A coloured unified diff."""

    def __init__(self, **options: str):
        """Creates an empty view.

        Args:
            **options (str): Textual's id and classes.
        """
        super().__init__('', **options)

    def show(self, difference: str) -> None:
        """Draws a diff.

        Args:
            difference (str): The unified diff text.
        """
        lines = []
        for line in difference.splitlines():
            if line.startswith(_FILE_MARKERS):
                lines.append(Content.from_markup('[b]$line[/b]', line=line))
            elif line.startswith('@@'):
                lines.append(
                    Content.from_markup('[$secondary]$line[/]', line=line)
                )
            elif line.startswith('+'):
                lines.append(
                    Content.from_markup('[$success]$line[/]', line=line)
                )
            elif line.startswith('-'):
                lines.append(Content.from_markup('[$error]$line[/]', line=line))
            else:
                lines.append(Content(line))
        self.update(Content('\n').join(lines))
