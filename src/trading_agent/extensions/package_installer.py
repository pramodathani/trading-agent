"""Installs and removes packages: `trading-agent packages install|remove`.

Installing copies the package's folder into workspace/shared/packages/<name>/; the desks, the hook runner and the MCP manager read its parts from there. Before copying, the installer checks that the folder holds at least one package part and that its mcp_servers.json is valid, and scans its text files for prompt injection. A package whose name is already installed is kept unless replacing is asked for.

Typical usage example:

  report = PackageInstaller(packages).install('https://github.com/someone/news-pack.git', replace=False)
"""

import dataclasses
import re
import shutil
import tempfile
from pathlib import Path

from trading_agent.extensions import injection_scanner
from trading_agent.extensions import (
    installed_packages as installed_packages_module,
)
from trading_agent.extensions import mcp_server_configuration
from trading_agent.extensions import source_fetcher

_NAME_PATTERN = re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')
_SCANNED_SUFFIXES = (
    '.md',
    '.txt',
)


class PackageError(RuntimeError):
    """A package could not be installed or removed, with the reason."""


@dataclasses.dataclass(frozen=True)
class InstallReport:
    """What one install did.

    Attributes:
        summary: The installed package's contents.
        replaced: Whether an installed package of the same name was replaced.
        warnings: Passages that look like prompt injection, and hook files that cannot run.
    """

    summary: installed_packages_module.PackageSummary
    replaced: bool
    warnings: tuple[str, ...]


class PackageInstaller:
    """Installs packages into the packages folder."""

    def __init__(self, packages: installed_packages_module.InstalledPackages):
        """Creates the installer.

        Args:
            packages (installed_packages_module.InstalledPackages): The installed packages.
        """
        self._packages = packages
        self._scanner = injection_scanner.InjectionScanner()

    def install(self, source: str, replace: bool) -> InstallReport:
        """Installs a package from a folder, a zip file or a git URL.

        Args:
            source (str): The package.
            replace (bool): Whether to replace an installed package of the same name.

        Returns:
            InstallReport: What was installed.

        Raises:
            PackageError: The source cannot be fetched, holds no package part, has an invalid name or mcp_servers.json, or is already installed.
        """
        with tempfile.TemporaryDirectory(prefix='package-install-') as scratch:
            try:
                folder = source_fetcher.SourceFetcher().local_folder(
                    source,
                    Path(scratch),
                )
            except source_fetcher.SourceError as error:
                raise PackageError(str(error)) from error
            name = self._name(folder, source)
            self._check_contents(folder)
            target = self._packages.packages_directory / name
            replaced = False
            if target.exists():
                if not replace:
                    raise PackageError(
                        f'A package named {name} is installed; use --replace to replace it.'
                    )
                shutil.rmtree(target)
                replaced = True
            self._packages.packages_directory.mkdir(parents=True, exist_ok=True)
            shutil.copytree(
                folder,
                target,
                ignore=shutil.ignore_patterns('.git'),
            )
        return InstallReport(
            summary=self._packages.summary(target),
            replaced=replaced,
            warnings=tuple(self._warnings(target)),
        )

    def remove(self, name: str) -> Path:
        """Deletes an installed package's folder.

        Args:
            name (str): The package's name.

        Returns:
            Path: The folder that was deleted.

        Raises:
            PackageError: No package of that name is installed.
        """
        target = self._packages.packages_directory / name
        if not _NAME_PATTERN.match(name) or not target.is_dir():
            raise PackageError(f'No package named {name} is installed.')
        shutil.rmtree(target)
        return target

    def _name(self, folder: Path, source: str) -> str:
        """The package's name: from package.toml, else from the source.

        Args:
            folder (Path): The fetched folder.
            source (str): The source as given, used when package.toml names nothing.

        Returns:
            str: The name.

        Raises:
            PackageError: The name is not 1 to 64 lower-case letters, digits, hyphens and underscores.
        """
        name = str(self._packages.manifest(folder).get('name', '')).strip()
        if not name:
            name = source.rstrip('/').split('/')[-1]
            for suffix in ('.git', '.zip'):
                name = name.removesuffix(suffix)
            name = name.lower()
        if not _NAME_PATTERN.match(name):
            raise PackageError(
                f'Package name {name!r} must be 1 to 64 lower-case letters, digits, hyphens and underscores; set [package] name in package.toml.'
            )
        return name

    def _check_contents(self, folder: Path) -> None:
        """Checks that the folder is a package and its MCP servers are valid.

        Args:
            folder (Path): The fetched folder.

        Raises:
            PackageError: It holds no package part, or its mcp_servers.json is invalid.
        """
        found = False
        for part in installed_packages_module.PARTS:
            if (folder / part).exists():
                found = True
        if not found:
            raise PackageError(
                f'{folder} is not a package: it has none of {", ".join(installed_packages_module.PARTS)}.'
            )
        servers_file = folder / 'mcp_servers.json'
        if servers_file.is_file():
            try:
                mcp_server_configuration.McpConfigurationReader(
                    servers_file
                ).read()
            except mcp_server_configuration.McpConfigurationError as error:
                raise PackageError(str(error)) from error

    def _warnings(self, target: Path) -> list[str]:
        """Scans the installed package's text files, and checks its hooks can run.

        Args:
            target (Path): The installed package's folder.

        Returns:
            list[str]: One line per problem found.
        """
        warnings = []
        for path in sorted(target.rglob('*')):
            if not path.is_file():
                continue
            relative = path.relative_to(target)
            is_hook = relative.parts[0] == 'hooks' and len(relative.parts) == 3
            executable = bool(path.stat().st_mode & 0o111)
            if is_hook and not executable:
                warnings.append(
                    f'{relative} is not executable, so it will never run.'
                )
            if path.suffix not in _SCANNED_SUFFIXES:
                continue
            text = path.read_text(encoding='utf-8', errors='replace')
            for finding in self._scanner.scan(text):
                warnings.append(
                    f'{relative}, line {finding.line_number}: {finding.rule} ("{finding.excerpt}")'
                )
        return warnings
