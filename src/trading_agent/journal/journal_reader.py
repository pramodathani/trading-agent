"""Reads the events a journal folder holds for one India date.

Typical usage example:

  reader = JournalReader(layout.trader_directory('general') / 'journal')
  events = reader.events(reader.today(), ['order', 'fill'])
"""

import datetime
import json
import zoneinfo
from collections.abc import Callable, Collection
from pathlib import Path
from typing import Any

_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')


class JournalReader:
    """The journal files of one trader, or of the gateway."""

    def __init__(
        self,
        folder: Path,
        clock: Callable[[], datetime.datetime] | None = None,
    ):
        """Creates the reader without reading anything.

        Args:
            folder (Path): The journal folder, holding one YYYY-MM-DD.jsonl file per India date.
            clock (Callable[[], datetime.datetime] | None): Returns the current time; None uses the system clock.
        """
        self._folder = folder
        self._clock = clock

    def today(self) -> str:
        """Today's India date, as the name its journal file uses.

        Returns:
            str: The date, such as "2026-10-19".
        """
        if self._clock is None:
            now = datetime.datetime.now(_INDIA)
        else:
            now = self._clock().astimezone(_INDIA)
        return now.date().isoformat()

    def events(
        self,
        day: str,
        kinds: Collection[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Reads one day's events, oldest first, skipping lines that are not JSON.

        Args:
            day (str): The India date, such as "2026-10-19".
            kinds (Collection[str] | None): The event kinds to keep, such as "order"; None keeps every kind.

        Returns:
            list[dict[str, Any]]: The events, each with kind, trader, payload and created_at. The list is empty when the day has no file.
        """
        path = self._folder / f'{day}.jsonl'
        if not path.is_file():
            return []
        events = []
        for line in path.read_text(encoding='utf-8').splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if kinds is None or event.get('kind') in kinds:
                events.append(event)
        return events
