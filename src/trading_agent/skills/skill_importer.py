"""Imports skills into the user's installed skills, from a folder, a zip file or a git repository.

Every folder in the source that holds a SKILL.md is imported as one skill, so a whole collection, such as a Hermes skills folder, can be imported at once. Each skill is checked before it is copied, and an existing skill of the same name is kept unless replacing is asked for.

Typical usage example:

  results = SkillImporter(installed_directory).import_source('~/.hermes/skills/research', replace=False)
"""

import dataclasses
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from trading_agent.skills import skill as skill_module

_GIT_PREFIXES = (
    'https://',
    'http://',
    'git@',
    'ssh://',
)


class SkillImportError(RuntimeError):
    """The source could not be read, cloned or unpacked."""


@dataclasses.dataclass(frozen=True)
class ImportResult:
    """What happened to one skill folder in the source.

    Attributes:
        source: The folder in the source.
        name: The skill's name, or None when its SKILL.md could not be read.
        outcome: "imported", "replaced", "skipped" or "invalid".
        detail: Why it was skipped or invalid, or an empty string.
    """

    source: Path
    name: str | None
    outcome: str
    detail: str


class SkillImporter:
    """Copies skills into the installed skills folder."""

    def __init__(self, installed_directory: Path):
        """Creates the importer.

        Args:
            installed_directory (Path): workspace/shared/skills/installed.
        """
        self._installed_directory = installed_directory
        self._parser = skill_module.SkillParser()

    def import_source(self, source: str, replace: bool) -> list[ImportResult]:
        """Imports every skill found in a folder, zip file or git URL.

        Args:
            source (str): The folder, the .zip file, or a git URL.
            replace (bool): Whether to replace installed skills of the same name.

        Returns:
            list[ImportResult]: One result per skill folder found.

        Raises:
            SkillImportError: The source does not exist, cannot be unpacked or cloned, or holds no SKILL.md.
        """
        with tempfile.TemporaryDirectory(prefix='skill-import-') as scratch:
            root = self._local_root(source, Path(scratch))
            folders = self._skill_folders(root)
            if not folders:
                raise SkillImportError(f'No SKILL.md found in {source}')
            results = []
            for folder in folders:
                results.append(self._import_folder(folder, replace))
            return results

    def _local_root(self, source: str, scratch: Path) -> Path:
        """Turns the source into a local folder.

        Args:
            source (str): The folder, zip file or git URL.
            scratch (Path): A temporary folder for unpacking or cloning.

        Returns:
            Path: The folder to search for skills.

        Raises:
            SkillImportError: The source cannot be used.
        """
        if source.startswith(_GIT_PREFIXES):
            return self._clone(source, scratch / 'clone')
        path = Path(source).expanduser()
        if path.is_file() and path.suffix == '.zip':
            return self._unzip(path, scratch / 'unzipped')
        if path.is_dir():
            return path
        raise SkillImportError(
            f'{source} is not a folder, a .zip file or a git URL'
        )

    def _clone(self, url: str, target: Path) -> Path:
        """Clones a git repository's latest commit.

        Args:
            url (str): The repository.
            target (Path): Where to clone it.

        Returns:
            Path: The clone.

        Raises:
            SkillImportError: git failed.
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
            raise SkillImportError(
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
            SkillImportError: The file is not a zip file, or an entry tries to escape the folder.
        """
        target.mkdir(parents=True)
        resolved_target = target.resolve()
        try:
            with zipfile.ZipFile(archive) as zip_file:
                for member in zip_file.namelist():
                    destination = (target / member).resolve()
                    if not destination.is_relative_to(resolved_target):
                        raise SkillImportError(
                            f'{archive} has an entry outside its folder: {member}'
                        )
                zip_file.extractall(target)
        except zipfile.BadZipFile as error:
            raise SkillImportError(f'{archive} is not a zip file') from error
        return target

    def _skill_folders(self, root: Path) -> list[Path]:
        """Finds every folder holding a SKILL.md, skipping git internals.

        Args:
            root (Path): The folder to search.

        Returns:
            list[Path]: The skill folders, sorted.
        """
        if (root / skill_module.SKILL_FILE_NAME).is_file():
            return [
                root,
            ]
        folders = []
        for path in sorted(root.rglob(skill_module.SKILL_FILE_NAME)):
            if '.git' in path.parts:
                continue
            folders.append(path.parent)
        return folders

    def _import_folder(self, folder: Path, replace: bool) -> ImportResult:
        """Checks and copies one skill folder.

        Args:
            folder (Path): The skill folder.
            replace (bool): Whether to replace an installed skill of the same name.

        Returns:
            ImportResult: What happened.
        """
        try:
            skill = self._parser.parse(folder, 'installed')
        except skill_module.SkillFormatError as error:
            return ImportResult(
                source=folder,
                name=None,
                outcome='invalid',
                detail=str(error),
            )
        target = self._installed_directory / skill.name
        outcome = 'imported'
        if target.exists():
            if not replace:
                return ImportResult(
                    source=folder,
                    name=skill.name,
                    outcome='skipped',
                    detail='already installed; use --replace to replace it',
                )
            shutil.rmtree(target)
            outcome = 'replaced'
        self._installed_directory.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            folder,
            target,
            ignore=shutil.ignore_patterns('.git'),
        )
        return ImportResult(
            source=folder,
            name=skill.name,
            outcome=outcome,
            detail='',
        )
