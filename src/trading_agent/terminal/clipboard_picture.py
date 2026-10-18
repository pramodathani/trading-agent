"""Saves a picture from the desktop clipboard, for Ctrl+V in the message box.

It asks wl-paste on Wayland, then xclip on X11 (which also serves Wayland through XWayland), for a PNG or JPEG on the clipboard. When neither has a picture, the message box pastes text as usual.

Typical usage example:

  path = ClipboardPicture().save(folder)
"""

import shutil
import subprocess
import time
from pathlib import Path

_TIMEOUT_SECONDS = 3
_PICTURE_TYPES = (
    (
        'image/png',
        '.png',
    ),
    (
        'image/jpeg',
        '.jpg',
    ),
)


class ClipboardPicture:
    """Reads a picture from the clipboard."""

    def save(self, folder: Path) -> Path | None:
        """Writes the clipboard's picture to a file.

        Args:
            folder (Path): Where to write it.

        Returns:
            Path | None: The picture's file, or None when the clipboard holds no picture or no clipboard program is installed.
        """
        for media_type, suffix in _PICTURE_TYPES:
            data = self._read(media_type)
            if data:
                folder.mkdir(parents=True, exist_ok=True)
                path = (
                    folder
                    / f'clipboard-{time.strftime("%Y%m%d-%H%M%S")}{suffix}'
                )
                path.write_bytes(data)
                return path
        return None

    def _read(self, media_type: str) -> bytes:
        """Reads one type from the clipboard.

        Args:
            media_type (str): Such as "image/png".

        Returns:
            bytes: The data, or empty bytes when the clipboard does not hold that type.
        """
        commands = []
        if shutil.which('wl-paste') is not None:
            commands.append(
                [
                    'wl-paste',
                    '--no-newline',
                    '--type',
                    media_type,
                ]
            )
        if shutil.which('xclip') is not None:
            commands.append(
                [
                    'xclip',
                    '-selection',
                    'clipboard',
                    '-target',
                    media_type,
                    '-out',
                ]
            )
        for command in commands:
            try:
                finished = subprocess.run(
                    command,
                    capture_output=True,
                    timeout=_TIMEOUT_SECONDS,
                    check=False,
                )
            except OSError, subprocess.TimeoutExpired:
                continue
            if finished.returncode == 0 and self._is_picture(finished.stdout):
                return finished.stdout
        return b''

    def _is_picture(self, data: bytes) -> bool:
        """Says whether bytes start like a PNG or a JPEG.

        Args:
            data (bytes): The clipboard's data.

        Returns:
            bool: True for a PNG or JPEG signature.
        """
        signatures = (
            b'\x89PNG',
            b'\xff\xd8',
        )
        return data.startswith(signatures)
