"""The side panel's Context card: how full the model's context window is, and with what.

A bar of coloured blocks shows each category's share, in the web page's swatch colours, followed by one row per category. Categories the model loads only when needed ("deferred") are listed apart.

Typical usage example:

  card = ContextCard()
  card.show(context_document)
"""

from typing import Any

from textual.content import Content

from trading_agent.terminal import formatter
from trading_agent.terminal.widgets import side_card

_FREE_SPACE = 'Free space'
_BAR_WIDTH = 36
_SWATCHES = {
    'Messages': '#3987e5',
    'System tools': '#d95926',
    'Tools': '#d95926',
    'MCP tools': '#d95926',
    'Memory files': '#199e70',
    'Autocompact buffer': '#5f5e5a',
}
_OTHER_SWATCH = '#97958d'
_DEFERRED_SWATCH = '#5f5e5a'


class ContextCard(side_card.SideCard):
    """The Context card."""

    def __init__(self, collapsed: bool = False):
        """Creates the card.

        Args:
            collapsed (bool): Whether it starts folded.
        """
        super().__init__('context', 'Context', collapsed=collapsed)
        self._formatter = formatter.Formatter()

    def show(self, usage: dict[str, Any] | None, error: str | None) -> None:
        """Shows the context window's use.

        Args:
            usage (dict[str, Any] | None): The usage snapshot, or None before the trader's first turn.
            error (str | None): Why it could not be read, or None.
        """
        if usage is None:
            self.show_aside('')
            self.show_body(
                self.note(error or "Shown after the trader's next turn.")
            )
            return
        window = max(int(usage.get('context_window') or 0), 1)
        total = int(usage.get('total_tokens') or 0)
        self.show_aside('' if usage.get('measured') else 'estimated')
        used = self._formatter.share(total, window).replace('.0%', '%')
        loaded = []
        deferred = []
        for category in usage.get('categories') or []:
            if category.get('deferred'):
                deferred.append(category)
            else:
                loaded.append(category)
        lines = [
            Content.from_markup(
                '[b]$used used[/b]  [dim]$tokens / $window[/dim]',
                used=used,
                tokens=self._formatter.token_count(total),
                window=self._formatter.token_count(window),
            ),
            self._bar(loaded, window),
        ]
        for category in loaded:
            lines.append(self._row(category, window))
        if deferred:
            lines.append(Content.from_markup('[dim]Loaded when needed[/dim]'))
            for category in deferred:
                lines.append(self._row(category, window))
        how = 'estimated from the conversation'
        if usage.get('measured'):
            how = 'measured by Claude Code'
        lines.append(
            self.note(
                f'{usage.get("backend", "")} · {how} at {self._formatter.time(str(usage.get("recorded_at", "")))}'
            )
        )
        self.show_body(Content('\n').join(lines))

    def _bar(self, categories: list[dict[str, Any]], window: int) -> Content:
        """A bar with one coloured run per category and the free space dimmed.

        Args:
            categories (list[dict[str, Any]]): The loaded categories.
            window (int): The context window's size.

        Returns:
            Content: The bar, _BAR_WIDTH cells wide.
        """
        parts = []
        filled = 0
        for category in categories:
            if category.get('name') == _FREE_SPACE:
                continue
            tokens = int(category.get('tokens') or 0)
            cells = round(_BAR_WIDTH * tokens / window)
            if tokens > 0 and cells == 0:
                cells = 1
            cells = min(cells, _BAR_WIDTH - filled)
            if cells <= 0:
                continue
            parts.append(('█' * cells, self._swatch(category)))
            filled += cells
        parts.append(('░' * (_BAR_WIDTH - filled), 'dim'))
        return Content.assemble(*parts)

    def _row(self, category: dict[str, Any], window: int) -> Content:
        """One category's row: its colour, name, tokens and share.

        Args:
            category (dict[str, Any]): The category.
            window (int): The context window's size.

        Returns:
            Content: The row.
        """
        tokens = int(category.get('tokens') or 0)
        share = '—'
        if not category.get('deferred'):
            share = self._formatter.share(tokens, window)
        name = str(category.get('name', ''))
        return Content.assemble(
            ('■ ', self._swatch(category)),
            name.ljust(20)[:20],
            self._formatter.token_count(tokens).rjust(7),
            ' ',
            (share.rjust(6), 'dim'),
        )

    def _swatch(self, category: dict[str, Any]) -> str:
        """A category's colour.

        Args:
            category (dict[str, Any]): The category.

        Returns:
            str: The colour as a hex style.
        """
        if category.get('deferred'):
            return _DEFERRED_SWATCH
        return _SWATCHES.get(str(category.get('name')), _OTHER_SWATCH)
