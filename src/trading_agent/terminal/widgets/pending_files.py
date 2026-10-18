"""The files waiting to go with the next message, shown on a line above the message box.

Each file is uploaded as soon as it is added, as on the web page, and shows "uploading…", "ready", "attached, but its text cannot be read", or why it failed. Backspace in the empty message box removes the newest file.

Typical usage example:

  tray = PendingFiles(gateway)
  tray.add('general', Path('chart.png'))
  ids = await tray.ready_ids()
"""

import asyncio
import dataclasses
import itertools
from pathlib import Path
from typing import Any

from textual import widgets
from textual import work
from textual.content import Content

from trading_agent.terminal import attachable_files
from trading_agent.terminal import gateway_client

_WAIT_STEP_SECONDS = 0.1
_LONGEST_WAIT_SECONDS = 120.0


@dataclasses.dataclass
class PendingFile:
    """One file added to the message being written.

    Attributes:
        local_id: A number for the file while it waits.
        path: The local file.
        status: "uploading", "ready" or "failed".
        attachment: The gateway's attachment once uploaded, or None.
        error: Why it failed, or None.
    """

    local_id: int
    path: Path
    status: str = 'uploading'
    attachment: dict[str, Any] | None = None
    error: str | None = None


class PendingFiles(widgets.Static):
    """The tray of files; hidden while empty."""

    def __init__(self, gateway: gateway_client.GatewayClient):
        """Creates the tray, empty.

        Args:
            gateway (gateway_client.GatewayClient): The gateway, to upload to.
        """
        super().__init__('', id='pending-files')
        self._gateway = gateway
        self._files: list[PendingFile] = []
        self._numbers = itertools.count(1)
        self._rules = attachable_files.AttachableFiles()

    def on_mount(self) -> None:
        """Hides the tray until a file is added."""
        self.display = False

    def add(self, desk_name: str, path: Path) -> str | None:
        """Adds a file and starts uploading it.

        Args:
            desk_name (str): The desk the message goes to.
            path (Path): The local file.

        Returns:
            str | None: Why the file cannot be attached, or None when it was added.
        """
        problem = self._rules.problem(path)
        if problem is not None:
            return problem
        pending = PendingFile(local_id=next(self._numbers), path=path)
        self._files.append(pending)
        self._show()
        self._upload(desk_name, pending)
        return None

    def remove_newest(self) -> bool:
        """Removes the newest file.

        Returns:
            bool: True when a file was removed.
        """
        if not self._files:
            return False
        self._files.pop()
        self._show()
        return True

    def has_files(self) -> bool:
        """Says whether any file waits.

        Returns:
            bool: True when the tray is not empty.
        """
        return bool(self._files)

    async def ready_ids(self) -> tuple[list[str], list[str]]:
        """Waits for the uploads to finish.

        Returns:
            tuple[list[str], list[str]]: The ids of the uploaded files, and the problems of the files that failed.
        """
        waited = 0.0
        while waited < _LONGEST_WAIT_SECONDS:
            uploading = False
            for pending in self._files:
                if pending.status == 'uploading':
                    uploading = True
            if not uploading:
                break
            await asyncio.sleep(_WAIT_STEP_SECONDS)
            waited += _WAIT_STEP_SECONDS
        ready = []
        problems = []
        for pending in self._files:
            if pending.status == 'ready' and pending.attachment is not None:
                ready.append(pending.attachment['attachment_id'])
            else:
                problems.append(
                    f'{pending.path.name}: {pending.error or "still uploading"}'
                )
        return ready, problems

    def clear(self) -> None:
        """Empties the tray after the message was sent."""
        self._files = []
        self._show()

    @work(group='upload')
    async def _upload(self, desk_name: str, pending: PendingFile) -> None:
        """Uploads one file.

        Args:
            desk_name (str): The desk.
            pending (PendingFile): The file.
        """
        try:
            pending.attachment = await self._gateway.upload_attachment(
                desk_name, pending.path
            )
        except (gateway_client.GatewayError, OSError) as error:
            pending.status = 'failed'
            pending.error = str(error)
            self._show()
            return
        pending.status = 'ready'
        self._show()

    def _show(self) -> None:
        """Redraws the tray."""
        self.display = bool(self._files)
        parts = []
        for pending in self._files:
            parts.append(
                Content.from_markup(
                    '📎 [b]$name[/b] [dim]$status[/dim]',
                    name=pending.path.name,
                    status=self._status_text(pending),
                )
            )
        if parts:
            parts.append(
                Content.from_markup(
                    '[dim]backspace in the empty box removes the newest[/dim]'
                )
            )
        self.update(Content('   ').join(parts))

    def _status_text(self, pending: PendingFile) -> str:
        """A file's state in words.

        Args:
            pending (PendingFile): The file.

        Returns:
            str: Such as "uploading…", "ready" or the failure.
        """
        if pending.status == 'uploading':
            return 'uploading…'
        if pending.status == 'failed':
            return f'failed: {pending.error}'
        attachment = pending.attachment or {}
        if attachment.get('problem'):
            return 'attached, but its text cannot be read'
        return 'ready'
