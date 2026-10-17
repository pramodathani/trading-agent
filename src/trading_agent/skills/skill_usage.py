"""Records each use of a skill, and whether the turn that used it went smoothly.

The tracker listens to the event bus, like the journal. A `load_skill` call opens a use; every failed tool call after it in the same turn counts against it; when the desk's turn finishes, the use is written as one JSON line to `workspace/desks/<desk>/skills/usage.jsonl`. A turn that ends in an error marks the use as failed.

"Went smoothly" is a rough signal, not a verdict: a tool can fail for reasons the skill did not cause. The curator reads these numbers as hints about which skills to review.

Typical usage example:

  tracker = SkillUsageTracker(event_bus, layout)
  task = asyncio.create_task(tracker.run())
  statistics = SkillUsageReader(usage_file).statistics()
"""

import dataclasses
import datetime
import json
import logging
from pathlib import Path

from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.workspace import workspace_layout

_LOGGER = logging.getLogger(__name__)
_LOAD_SKILL_TOOL_NAME = 'load_skill'
_QUEUE_SIZE = 10000


@dataclasses.dataclass
class _OpenUse:
    """A skill loaded in a turn that has not finished yet.

    Attributes:
        skill: The skill's name.
        call_id: The load_skill call's identifier.
        trigger_id: The turn's trigger.
        tool_errors: How many tool calls failed after the skill was loaded.
    """

    skill: str
    call_id: str
    trigger_id: str
    tool_errors: int = 0


@dataclasses.dataclass(frozen=True)
class SkillStatistics:
    """How one skill has been used.

    Attributes:
        uses: How many turns loaded it.
        troubled_uses: How many of those turns had failed tool calls after loading it, or ended in an error.
        last_used: The ISO 8601 time of the last use.
    """

    uses: int
    troubled_uses: int
    last_used: str


class SkillUsageTracker:
    """Turns the event stream into skill-use records."""

    def __init__(
        self,
        event_bus: event_bus_module.EventBus,
        layout: workspace_layout.WorkspaceLayout,
    ):
        """Subscribes to the bus at once, so no load_skill call is missed.

        Args:
            event_bus (event_bus_module.EventBus): The bus to listen to.
            layout (workspace_layout.WorkspaceLayout): Where each desk's usage file goes.
        """
        self._layout = layout
        self._subscription = event_bus.subscribe(maximum_queued=_QUEUE_SIZE)
        self._open_uses: dict[str, list[_OpenUse]] = {}
        self._failed_desks = set()

    async def run(self) -> None:
        """Handles events until the task is cancelled."""
        try:
            while True:
                published_event = await self._subscription.next_event()
                self.handle(published_event)
        finally:
            self._subscription.close()

    def handle(self, published_event: event_module.Event) -> None:
        """Updates the open uses with one event.

        Args:
            published_event (event_module.Event): The event.
        """
        desk = published_event.desk
        if desk is None:
            return
        kind = published_event.kind
        payload = published_event.payload
        if kind == event_module.EventKind.TOOL_CALL:
            if payload.get('name') == _LOAD_SKILL_TOOL_NAME:
                arguments = payload.get('arguments') or {}
                self._open_uses.setdefault(desk, []).append(
                    _OpenUse(
                        skill=str(arguments.get('name', '')),
                        call_id=str(payload.get('call_id', '')),
                        trigger_id=str(payload.get('trigger_id', '')),
                    )
                )
        elif kind == event_module.EventKind.TOOL_RESULT:
            self._count_result(desk, payload)
        elif kind == event_module.EventKind.ERROR:
            if self._open_uses.get(desk):
                self._failed_desks.add(desk)
        elif kind == event_module.EventKind.TURN_FINISHED:
            self._finish(desk)

    def _count_result(self, desk: str, payload: dict) -> None:
        """Drops a use whose load failed, and counts other failed calls against open uses.

        Args:
            desk (str): The desk.
            payload (dict): The tool_result event's payload.
        """
        if not payload.get('is_error'):
            return
        open_uses = self._open_uses.get(desk, [])
        call_id = payload.get('call_id')
        kept = []
        for use in open_uses:
            if use.call_id == call_id:
                continue
            kept.append(use)
        if len(kept) != len(open_uses):
            self._open_uses[desk] = kept
            return
        for use in open_uses:
            use.tool_errors += 1

    def _finish(self, desk: str) -> None:
        """Writes the desk's open uses when its turn ends.

        Turns run one at a time per desk, so every open use belongs to the turn that just ended, or to a rollover or compression turn inside it.

        Args:
            desk (str): The desk.
        """
        open_uses = self._open_uses.pop(desk, [])
        turn_failed = desk in self._failed_desks
        self._failed_desks.discard(desk)
        if not open_uses:
            return
        path = self._layout.skill_usage_file(desk)
        now = datetime.datetime.now(datetime.UTC).isoformat()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('a', encoding='utf-8') as usage_file:
                for use in open_uses:
                    record = {
                        'at': now,
                        'skill': use.skill,
                        'trigger_id': use.trigger_id,
                        'tool_errors_after': use.tool_errors,
                        'turn_failed': turn_failed,
                    }
                    usage_file.write(json.dumps(record) + '\n')
        except OSError:
            _LOGGER.exception('Could not write skill usage to %s', path)


class SkillUsageReader:
    """Summarises one desk's usage file."""

    def __init__(self, usage_file: Path):
        """Creates the reader.

        Args:
            usage_file (Path): The desk's usage.jsonl.
        """
        self._usage_file = usage_file

    def statistics(self) -> dict[str, SkillStatistics]:
        """Counts each skill's uses.

        Returns:
            dict[str, SkillStatistics]: The statistics, keyed by skill name; skills never used are absent.
        """
        uses = {}
        troubled = {}
        last_used = {}
        if not self._usage_file.is_file():
            return {}
        for line in self._usage_file.read_text(encoding='utf-8').splitlines():
            try:
                record = json.loads(line)
            except ValueError:
                continue
            name = record.get('skill', '')
            uses[name] = uses.get(name, 0) + 1
            if record.get('tool_errors_after') or record.get('turn_failed'):
                troubled[name] = troubled.get(name, 0) + 1
            last_used[name] = max(last_used.get(name, ''), record.get('at', ''))
        statistics = {}
        for name, count in uses.items():
            statistics[name] = SkillStatistics(
                uses=count,
                troubled_uses=troubled.get(name, 0),
                last_used=last_used[name],
            )
        return statistics
