"""Searches the traders' journals for proof that something has already happened, for the going-live checks.

Typical usage example:

  event = JournalSearch(layout, ['main']).latest('order', 'dry_run', True)
"""

import json
from collections.abc import Sequence
from typing import Any

from trading_agent.workspace import workspace_layout


class JournalSearch:
    """Reads every trader's journal files, newest day first."""

    def __init__(
        self,
        layout: workspace_layout.WorkspaceLayout,
        trader_names: Sequence[str],
    ):
        """Creates the search.

        Args:
            layout (workspace_layout.WorkspaceLayout): Where the traders' folders are.
            trader_names (Sequence[str]): The traders to search.
        """
        self._layout = layout
        self._trader_names = list(trader_names)

    def events(self, kind: str) -> list[dict[str, Any]]:
        """Every journaled event of one kind, from every trader, newest day first.

        Args:
            kind (str): The event kind, such as "order".

        Returns:
            list[dict[str, Any]]: The events as the journal stores them.
        """
        found = []
        for trader_name in self._trader_names:
            folder = self._layout.trader_directory(trader_name) / 'journal'
            if not folder.is_dir():
                continue
            for path in sorted(folder.glob('*.jsonl'), reverse=True):
                for line in path.read_text(encoding='utf-8').splitlines():
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if event.get('kind') == kind:
                        found.append(event)
        found.sort(key=self._time_of, reverse=True)
        return found

    def _time_of(self, event: dict[str, Any]) -> str:
        """An event's time, for sorting.

        Args:
            event (dict[str, Any]): The event.

        Returns:
            str: Its created_at, or an empty string.
        """
        return str(event.get('created_at', ''))
