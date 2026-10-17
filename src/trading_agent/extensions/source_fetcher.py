"""Turns a folder, a zip file or a git URL into a local folder, for imports and installs.

Both `trading-agent skills import` and `trading-agent packages install` accept the same three kinds of source, so this one class fetches them.

Typical usage example:

  with tempfile.TemporaryDirectory() as scratch:
      folder = SourceFetcher().local_folder('https://github.com/someone/skills.git', Path(scratch))
"""

import subprocess
import zipfile
from pathlib import Path

_GIT_PREFIXES = (
    'https://',
    'http://',
    'git@',
    'ssh://',
)


class SourceError(RuntimeError):
    """The source does not exist, or cannot be cloned or unpacked."""


class SourceFetcher:
    """Fetches import sources."""

    def local_folder(self, source: str, scratch: Path) -> Path:
        """Turns a source into a local folder.

        Args:
            source (str): A folder, a .zip file, or a git URL.
            scratch (Path): A temporary folder for unpacking or cloning, which the caller deletes.

        Returns:
            Path: The folder, which for a local folder is the folder itself.

        Raises:
            SourceError: The source cannot be used.
        """
        if self.is_git_url(source):
            return self._clone(source, scratch / 'clone')
        path = Path(source).expanduser()
        if path.is_file() and path.suffix == '.zip':
            return self._unzip(path, scratch / 'unzipped')
        if path.is_dir():
            return path
        raise SourceError(f'{source} is not a folder, a .zip file or a git URL')

    def is_git_url(self, source: str) -> bool:
        """Says whether a source is a git URL.

        Args:
            source (str): The source.

        Returns:
            bool: True for http, https, ssh and git@ addresses.
        """
        return source.startswith(_GIT_PREFIXES)

    def _clone(self, url: str, target: Path) -> Path:
        """Clones a git repository's latest commit.

        Args:
            url (str): The repository.
            target (Path): Where to clone it.

        Returns:
            Path: The clone.

        Raises:
            SourceError: git failed.
        """
        completed = subprocess.run(
            [
                'git',
                'clone',
                '--depth',
                '1',
                '--quiet',
                url,
                str(target),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise SourceError(
                f'git clone {url} failed: {completed.stderr.strip()}'
            )
        return target

    def _unzip(self, archive: Path, target: Path) -> Path:
        """Unpacks a zip file, refusing entries that would land outside the target.

        Args:
            archive (Path): The zip file.
            target (Path): Where to unpack it.

        Returns:
            Path: The unpacked folder.

        Raises:
            SourceError: The file is not a zip file, or an entry tries to escape the folder.
        """
        target.mkdir(parents=True)
        resolved_target = target.resolve()
        try:
            with zipfile.ZipFile(archive) as zip_file:
                for member in zip_file.namelist():
                    destination = (target / member).resolve()
                    if not destination.is_relative_to(resolved_target):
                        raise SourceError(
                            f'{archive} has an entry outside its folder: {member}'
                        )
                zip_file.extractall(target)
        except zipfile.BadZipFile as error:
            raise SourceError(f'{archive} is not a zip file') from error
        return target
