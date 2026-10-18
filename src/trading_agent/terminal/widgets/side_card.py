"""One foldable card of the side panel, with rows of a label and a value.

Each card of the panel is its own subclass, which fills the body with `show_body`.

Typical usage example:

  class FundsCard(SideCard):
      ...
      self.show_body(self.rows([('Balance', '₹60,602.56')]))
"""

from collections.abc import Sequence

from textual import widgets
from textual.content import Content

_LABEL_WIDTH = 20
_VALUE_WIDTH = 16

Row = tuple[str, str | Content]


class SideCard(widgets.Collapsible):
    """A side panel card.

    Attributes:
        card_id: The card's short name, such as "funds", used to remember whether it is folded.
    """

    def __init__(
        self,
        card_id: str,
        title: str,
        *extra: widgets.Widget,
        collapsed: bool = False,
    ):
        """Creates the card with an empty body.

        Args:
            card_id (str): The card's short name.
            title (str): The card's title.
            *extra (widgets.Widget): Widgets shown under the body, such as a list.
            collapsed (bool): Whether the card starts folded.
        """
        self.card_id = card_id
        self._card_title = title
        self._body = widgets.Static('', classes='side-body')
        super().__init__(
            self._body,
            *extra,
            title=title,
            collapsed=collapsed,
            id=f'card-{card_id}',
            classes='side-card',
        )

    def show_body(self, content: Content | str) -> None:
        """Replaces the card's body.

        Args:
            content (Content | str): The new body.
        """
        self._body.update(content)

    def show_aside(self, aside: str) -> None:
        """Puts a short note after the title, such as a count or "DRY RUN".

        Args:
            aside (str): The note, or an empty string for none.
        """
        if aside:
            self.title = f'{self._card_title} · {aside}'
        else:
            self.title = self._card_title

    def rows(self, rows: Sequence[Row]) -> Content:
        """Lays out rows of a label and a value.

        Args:
            rows (Sequence[Row]): The rows; a value may carry its own colour.

        Returns:
            Content: One line per row, the label padded and the value aligned right.
        """
        lines = []
        for label, value in rows:
            if isinstance(value, Content):
                shown = value
            else:
                shown = Content(str(value))
            padding = max(1, _VALUE_WIDTH - shown.cell_length)
            lines.append(
                Content.assemble(
                    (label.ljust(_LABEL_WIDTH), 'dim'),
                    ' ' * padding,
                    shown,
                )
            )
        return Content('\n').join(lines)

    def note(self, text: str) -> Content:
        """A muted note line.

        Args:
            text (str): The note.

        Returns:
            Content: The dimmed text.
        """
        return Content.from_markup('[dim]$text[/dim]', text=text)
