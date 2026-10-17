"""Imports skills into the user's installed skills, from a folder, a zip file or a git repository.

Every folder in the source that holds a SKILL.md is imported as one skill, so a whole collection, such as a Hermes skills folder, can be imported at once. Each skill is checked before it is copied, and an existing skill of the same name is kept unless replacing is asked for.

Typical usage example:

  results = SkillImporter(installed_directory).import_source('~/.hermes/skills/research', replace=False)
"""

import dataclasses
import shutil
import tempfile
from pathlib import Path

from trading_agent.extensions import injection_scanner
from trading_agent.extensions import source_fetcher
from trading_agent.skills import skill as skill_module

_SCANNED_SUFFIXES = (
    '.md',
    '.txt',
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
        warnings: Passages that look like prompt injection, as "file, line: what it looks like".
    """

    source: Path
    name: str | None
    outcome: str
    detail: str
    warnings: tuple[str, ...] = ()


class SkillImporter:
    """Copies skills into the installed skills folder."""

    def __init__(self, installed_directory: Path):
        """Creates the importer.

        Args:
            installed_directory (Path): workspace/shared/skills/installed.
        """
        self._installed_directory = installed_directory
        self._parser = skill_module.SkillParser()
        self._scanner = injection_scanner.InjectionScanner()

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
            try:
                root = source_fetcher.SourceFetcher().local_folder(
                    source,
                    Path(scratch),
                )
            except source_fetcher.SourceError as error:
                raise SkillImportError(str(error)) from error
            folders = self._skill_folders(root)
            if not folders:
                raise SkillImportError(f'No SKILL.md found in {source}')
            results = []
            for folder in folders:
                results.append(self._import_folder(folder, replace))
            return results

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
            warnings=self._warnings(folder),
        )

    def _warnings(self, folder: Path) -> tuple[str, ...]:
        """Scans a skill's text files for prompt injection.

        The skill is still imported, because the user decides; the warnings tell them what to read before relying on it.

        Args:
            folder (Path): The skill's folder.

        Returns:
            tuple[str, ...]: One line per finding.
        """
        warnings = []
        for path in sorted(folder.rglob('*')):
            if not path.is_file() or path.suffix not in _SCANNED_SUFFIXES:
                continue
            if '.git' in path.parts:
                continue
            text = path.read_text(encoding='utf-8', errors='replace')
            for finding in self._scanner.scan(text):
                warnings.append(
                    f'{path.relative_to(folder)}, line {finding.line_number}: {finding.rule} ("{finding.excerpt}")'
                )
        return tuple(warnings)
