"""The add_note tool: records one to three short lessons in the desk's notes for today.

Notes go to `notes/YYYY-MM-DD.md` in the desk folder, one bullet per note with the India time. When a session ends, the desk folds the day's notes into Memory.md. The notes file is snapshotted before every change, so a note can be undone.

Typical usage example:

  tool = AddNoteTool(notes_directory, checkpoints)
"""

import asyncio
import datetime
import logging
import zoneinfo
from collections.abc import Callable
from pathlib import Path

import pydantic

from trading_agent.memory import checkpoints as checkpoints_module
from trading_agent.tools import tool

_LOGGER = logging.getLogger(__name__)
_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')


class AddNoteArguments(pydantic.BaseModel):
    """The arguments of add_note.

    Attributes:
        notes: One to three short notes, each a single lesson.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    notes: list[str] = pydantic.Field(min_length=1, max_length=3)

    @pydantic.field_validator('notes')
    @classmethod
    def _require_short_single_line_notes(cls, notes: list[str]) -> list[str]:
        """Checks that each note is a non-empty line of at most 500 characters.

        Args:
            notes (list[str]): The notes.

        Returns:
            list[str]: The notes, stripped of surrounding spaces.

        Raises:
            ValueError: A note is empty, too long or spans several lines.
        """
        cleaned = []
        for note in notes:
            text = note.strip()
            if not text:
                raise ValueError('A note cannot be empty')
            if len(text) > 500:
                raise ValueError('Each note must be at most 500 characters')
            if '\n' in text:
                raise ValueError('Each note must be a single line')
            cleaned.append(text)
        return cleaned


class AddNoteTool(tool.Tool):
    """Appends notes to today's notes file."""

    name = 'add_note'
    description = "Records one to three short notes in today's notes file (notes/YYYY-MM-DD.md). Use it after a turn in which you learned something worth keeping: about the market, your strategy, a tool, a mistake, or the user's wishes. Each note is one specific lesson on one line, such as 'IDEA's spread widens past 0.10 after 15:00; use limit orders then'. Skip routine turns. When the session ends you fold the day's notes into Memory.md."
    arguments_model = AddNoteArguments

    def __init__(
        self,
        notes_directory: Path,
        checkpoints: checkpoints_module.Checkpoints | None,
        clock: Callable[[], datetime.datetime] | None = None,
    ):
        """Creates the tool.

        Args:
            notes_directory (Path): The desk's notes folder.
            checkpoints (checkpoints_module.Checkpoints | None): Snapshots the desk's files before the note is written, or None to take none.
            clock (Callable[[], datetime.datetime] | None): Returns the current India time; None uses the system clock. Tests replace it.
        """
        self._notes_directory = notes_directory
        self._checkpoints = checkpoints
        self._clock = clock

    async def run(self, arguments: AddNoteArguments) -> tool.ToolResult:
        """Appends the notes, starting today's file when needed.

        Args:
            arguments (AddNoteArguments): The notes.

        Returns:
            tool.ToolResult: Where the notes went.
        """
        now = self._now()
        path = self._notes_directory / f'{now.date().isoformat()}.md'
        if self._checkpoints is not None:
            try:
                await asyncio.to_thread(
                    self._checkpoints.snapshot,
                    f'before add_note notes/{path.name}',
                )
            except checkpoints_module.CheckpointError:
                _LOGGER.exception('Could not snapshot before add_note')
        lines = []
        if not path.exists():
            lines.append(f'# Notes for {now.date().isoformat()}')
            lines.append('')
        for note in arguments.notes:
            lines.append(f'- {now:%H:%M} {note}')
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a', encoding='utf-8') as notes_file:
            notes_file.write('\n'.join(lines) + '\n')
        return tool.ToolResult.success(
            f'Added {len(arguments.notes)} note(s) to notes/{path.name}.'
        )

    def _now(self) -> datetime.datetime:
        """The current India time.

        Returns:
            datetime.datetime: The time.
        """
        if self._clock is not None:
            return self._clock()
        return datetime.datetime.now(_INDIA)
