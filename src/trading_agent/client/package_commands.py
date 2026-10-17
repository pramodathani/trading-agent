"""The `trading-agent packages` commands: install, list and remove.

Typical usage example:

  exit_code = PackageCommands(packages).run('install', 'https://github.com/someone/news-pack.git', replace=False)
"""

import sys
from typing import TextIO

from trading_agent.extensions import (
    installed_packages as installed_packages_module,
)
from trading_agent.extensions import package_installer


class PackageCommands:
    """Installs, lists and removes packages for the user."""

    def __init__(
        self,
        packages: installed_packages_module.InstalledPackages,
        output: TextIO = sys.stdout,
    ):
        """Creates the commands.

        Args:
            packages (installed_packages_module.InstalledPackages): The installed packages.
            output (TextIO): Where to print.
        """
        self._packages = packages
        self._installer = package_installer.PackageInstaller(packages)
        self._output = output

    def run(self, action: str, argument: str | None, replace: bool) -> int:
        """Runs one action.

        Args:
            action (str): "install", "list" or "remove".
            argument (str | None): The source for "install", the name for "remove".
            replace (bool): For "install", whether to replace an installed package of the same name.

        Returns:
            int: 0 on success, 1 when the install or removal was refused.
        """
        try:
            if action == 'install':
                self._install(argument, replace)
            elif action == 'remove':
                folder = self._installer.remove(argument)
                self._print(
                    f'Removed {argument} ({folder}). Restart the gateway to stop its MCP servers.'
                )
            else:
                self._list()
        except package_installer.PackageError as error:
            self._print(str(error))
            return 1
        return 0

    def _install(self, source: str, replace: bool) -> None:
        """Installs a package and prints what it brought.

        Args:
            source (str): The folder, zip file or git URL.
            replace (bool): Whether to replace an installed package of the same name.
        """
        report = self._installer.install(source, replace)
        verb = 'Replaced' if report.replaced else 'Installed'
        self._print(
            f'{verb} {report.summary.name}: {report.summary.describe()}.'
        )
        for warning in report.warnings:
            self._print(f'  warning: {warning}')
        self._print(
            'Skills and hooks take effect at once; restart the gateway to start its MCP servers.'
        )
        if report.summary.has_app:
            self._print(
                f"Its app appears in the web page's sidebar under Apps. If its service is not set up yet, run: trading-agent apps enable {report.summary.name}"
            )

    def _list(self) -> None:
        """Prints one line per installed package."""
        folders = self._packages.folders()
        if not folders:
            self._print('No packages installed.')
            return
        for folder in folders:
            summary = self._packages.summary(folder)
            version = f' {summary.version}' if summary.version else ''
            self._print(f'{summary.name}{version}: {summary.describe()}')
            if summary.description:
                self._print(f'  {summary.description}')

    def _print(self, text: str) -> None:
        """Prints one line.

        Args:
            text (str): The line.
        """
        print(text, file=self._output)
