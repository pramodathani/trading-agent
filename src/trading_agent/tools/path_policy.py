"""Decides which files a desk's file tools may read and write.

A relative path is taken from the desk's own folder, so "Memory.md" and "notes/today.md" mean the desk's files. Every path is resolved to where it really is before it is checked, so neither "../" nor a link can lead outside the allowed places.

- Reading is allowed anywhere except the hidden secret files and folders that the bash sandbox also hides.
- Writing is allowed only in the desk's memory, notes and scratch folders and its Memory.md. The user's files can only be changed through propose_file_change.

Typical usage example:

  policy = PathPolicy(desk_directory, hidden_paths)
  path = policy.readable('Memory.md')
"""

from collections.abc import Sequence
from pathlib import Path

_WRITABLE_FOLDER_NAMES = (
    'memory',
    'notes',
    'scratch',
)
_WRITABLE_FILE_NAMES = ('Memory.md',)


class PathRefusedError(ValueError):
    """A file tool asked for a path it may not use."""


class PathPolicy:
    """The read and write rules for one desk's file tools.

    Attributes:
        desk_directory: The desk's own folder, where relative paths start.
    """

    def __init__(self, desk_directory: Path, hidden_paths: Sequence[Path]):
        """Creates the policy.

        Args:
            desk_directory (Path): The desk's own folder.
            hidden_paths (Sequence[Path]): Resolved secret files and folders that may not be read.
        """
        self.desk_directory = desk_directory.resolve()
        self._hidden_paths = [Path(path).resolve() for path in hidden_paths]

    def readable(self, requested: str) -> Path:
        """Resolves a path the desk wants to read.

        Args:
            requested (str): The path as the model wrote it.

        Returns:
            Path: The resolved path.

        Raises:
            PathRefusedError: The path is, or is inside, a hidden secret.
        """
        path = self._resolve(requested)
        for hidden in self._hidden_paths:
            if path == hidden or path.is_relative_to(hidden):
                raise PathRefusedError(
                    f'{requested} holds secrets and cannot be read.'
                )
        return path

    def writable(self, requested: str) -> Path:
        """Resolves a path the desk wants to write.

        Args:
            requested (str): The path as the model wrote it.

        Returns:
            Path: The resolved path.

        Raises:
            PathRefusedError: The path is outside the desk's own writable places.
        """
        path = self._resolve(requested)
        for file_name in _WRITABLE_FILE_NAMES:
            if path == self.desk_directory / file_name:
                return path
        for folder_name in _WRITABLE_FOLDER_NAMES:
            folder = self.desk_directory / folder_name
            if path != folder and path.is_relative_to(folder):
                return path
        raise PathRefusedError(
            f"{requested} cannot be written. You may write only inside memory/, notes/ and scratch/ of your desk folder, and your Memory.md. Propose changes to the user's files with propose_file_change."
        )

    def _resolve(self, requested: str) -> Path:
        """Turns the model's path into a real, absolute one.

        Args:
            requested (str): The path as the model wrote it.

        Returns:
            Path: The absolute path with every link and ".." resolved.
        """
        path = Path(requested).expanduser()
        if not path.is_absolute():
            path = self.desk_directory / path
        return path.resolve()
