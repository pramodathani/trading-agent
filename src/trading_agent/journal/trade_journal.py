"""The trade journal: a permanent, append-only record of everything each desk does.

The journal listens to the event bus and writes each event as one JSON line in the desk's file for that India date, `workspace/desks/<desk>/journal/YYYY-MM-DD.jsonl`; events that belong to no desk go to `workspace/journal/`. Lines are only ever added. Secrets are masked first. The stream of individual text pieces is left out, because the final text event of the turn holds the whole reply.

Typical usage example:

  journal = TradeJournal(event_bus, layout, redactor)
  task = asyncio.create_task(journal.run())
"""

import json
import logging
import zoneinfo
from pathlib import Path

from trading_agent.journal import secret_redactor as secret_redactor_module
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.workspace import workspace_layout

_LOGGER = logging.getLogger(__name__)
_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')
_JOURNAL_QUEUE_SIZE = 100000
_SKIPPED_KINDS = (event_module.EventKind.TEXT_DELTA,)


class TradeJournal:
    """Writes every event to the desks' journal files."""

    def __init__(
        self,
        event_bus: event_bus_module.EventBus,
        layout: workspace_layout.WorkspaceLayout,
        redactor: secret_redactor_module.SecretRedactor,
    ):
        """Subscribes to the bus at once, so no event published after this is missed.

        Args:
            event_bus (event_bus_module.EventBus): The bus to record.
            layout (workspace_layout.WorkspaceLayout): Where the journal files go.
            redactor (secret_redactor_module.SecretRedactor): Masks secrets before writing.
        """
        self._layout = layout
        self._redactor = redactor
        self._subscription = event_bus.subscribe(
            maximum_queued=_JOURNAL_QUEUE_SIZE
        )

    async def run(self) -> None:
        """Writes events until the task is cancelled, then stops listening."""
        try:
            while True:
                published_event = await self._subscription.next_event()
                self.record(published_event)
        finally:
            if self._subscription.dropped_count:
                _LOGGER.error(
                    'The journal dropped %d events because it fell behind',
                    self._subscription.dropped_count,
                )
            self._subscription.close()

    def record(self, published_event: event_module.Event) -> None:
        """Appends one event to its journal file, unless it is a text piece.

        A failure to write is logged and does not stop the journal.

        Args:
            published_event (event_module.Event): The event.
        """
        if published_event.kind in _SKIPPED_KINDS:
            return
        line = json.dumps(
            self._redactor.redact(published_event.to_json_dictionary()),
            ensure_ascii=False,
            default=str,
        )
        path = self.path_for(published_event)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('a', encoding='utf-8') as journal_file:
                journal_file.write(line + '\n')
        except OSError:
            _LOGGER.exception('Could not write to the journal %s', path)

    def path_for(self, published_event: event_module.Event) -> Path:
        """The journal file an event belongs in.

        Args:
            published_event (event_module.Event): The event.

        Returns:
            Path: The desk's file for the event's India date, or the gateway's file for an event without a desk.
        """
        day = published_event.created_at.astimezone(_INDIA).date().isoformat()
        if published_event.desk is None:
            return self._layout.root / 'journal' / f'{day}.jsonl'
        return (
            self._layout.desk_directory(published_event.desk)
            / 'journal'
            / f'{day}.jsonl'
        )
