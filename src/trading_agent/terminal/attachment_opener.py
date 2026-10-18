"""Downloads a file the desk sent, or a picture a tool showed it, and opens it with the desktop's default program.

Files are saved under the state folder's "downloads" folder and opened with xdg-open, so a picture opens in the image viewer and a PDF in the PDF reader, as a new browser tab does on the web page.

Typical usage example:

  opener = AttachmentOpener(gateway)
  path = await opener.open_attachment('general', attachment)
"""

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from trading_agent.terminal import gateway_client
from trading_agent.terminal import terminal_settings

_UNSAFE_CHARACTERS = re.compile(r'[^A-Za-z0-9._-]+')


class AttachmentOpener:
    """Saves desk files locally and opens them."""

    def __init__(
        self,
        gateway: gateway_client.GatewayClient,
        folder: Path | None = None,
    ):
        """Creates the opener.

        Args:
            gateway (gateway_client.GatewayClient): The gateway, to download from.
            folder (Path | None): Where to save files, or None for the state folder's "downloads" folder.
        """
        self._gateway = gateway
        if folder is None:
            folder = (
                terminal_settings.TerminalSettings.state_directory()
                / 'downloads'
            )
        self.folder = folder

    async def save_attachment(
        self, desk_name: str, attachment: dict[str, Any]
    ) -> Path:
        """Downloads an attachment.

        Args:
            desk_name (str): The desk it belongs to.
            attachment (dict[str, Any]): The attachment, with attachment_id and file_name.

        Returns:
            Path: Where it was saved.

        Raises:
            gateway_client.GatewayError: The gateway could not send it.
            OSError: The file could not be written.
        """
        data = await self._gateway.attachment_bytes(
            desk_name, attachment['attachment_id']
        )
        name = f'{attachment["attachment_id"]}-{attachment.get("file_name", "file")}'
        return self._write(name, data)

    async def save_picture(self, desk_name: str, picture_path: str) -> Path:
        """Downloads a picture from inside a desk's folder.

        Args:
            desk_name (str): The desk.
            picture_path (str): The picture's path relative to the desk folder.

        Returns:
            Path: Where it was saved.

        Raises:
            gateway_client.GatewayError: The gateway could not send it.
            OSError: The file could not be written.
        """
        data = await self._gateway.picture_bytes(desk_name, picture_path)
        return self._write(f'{desk_name}-{picture_path}', data)

    def open(self, path: Path) -> bool:
        """Opens a saved file with the desktop's default program, without waiting for it.

        Args:
            path (Path): The file.

        Returns:
            bool: True when xdg-open was started, False when it is not installed.
        """
        program = shutil.which('xdg-open')
        if program is None:
            return False
        subprocess.Popen(
            [
                program,
                str(path),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True

    def _write(self, name: str, data: bytes) -> Path:
        """Writes downloaded bytes under a safe file name.

        Args:
            name (str): The wanted name, which may hold unsafe characters.
            data (bytes): The contents.

        Returns:
            Path: Where they were written.

        Raises:
            OSError: The file could not be written.
        """
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / _UNSAFE_CHARACTERS.sub('_', name)
        path.write_bytes(data)
        return path
