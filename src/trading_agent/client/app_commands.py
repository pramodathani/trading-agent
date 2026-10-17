"""The `trading-agent apps` commands: list the packages' apps, and enable or disable their systemd units.

Enabling links the unit file the app's app.toml names (when systemd does not know the unit yet), then enables and starts it, so the app starts at every login. This is a command rather than a web page button, because it adds a program to the machine's start-up.

Typical usage example:

  exit_code = asyncio.run(AppCommands(catalog).enable('sridhara'))
"""

import sys
from typing import TextIO

from trading_agent.extensions import app_catalog as app_catalog_module
from trading_agent.extensions import systemd_user_units


class AppCommands:
    """Lists and sets up the packages' apps for the user."""

    def __init__(
        self,
        catalog: app_catalog_module.AppCatalog,
        output: TextIO = sys.stdout,
    ):
        """Creates the commands.

        Args:
            catalog (app_catalog_module.AppCatalog): The packages' apps.
            output (TextIO): Where to print.
        """
        self._catalog = catalog
        self._output = output

    async def list(self) -> int:
        """Prints each app with its address, whether it answers and its unit's state.

        Returns:
            int: 0 when every app.toml is readable, 1 otherwise.
        """
        apps = self._catalog.apps()
        if not apps:
            self._print('No installed package has an app.')
        failed = False
        for app in apps:
            if app.manifest is None:
                self._print(f'{app.package}: cannot read app.toml: {app.error}')
                failed = True
                continue
            status = await self._catalog.status(app)
            health = (
                'answers'
                if status.healthy
                else f'does not answer ({status.health_detail})'
            )
            self._print(
                f'{app.package}: {app.manifest.app.title} at {app.manifest.app.url}, {health}'
            )
            if status.unit_state is not None:
                state = status.unit_state
                self._print(
                    f'  unit {app.manifest.service.unit}: {state.load_state}, {state.active_state} ({state.sub_state})'
                )
            elif status.unit_error:
                self._print(f'  unit: {status.unit_error}')
        if failed:
            return 1
        return 0

    async def enable(self, package: str) -> int:
        """Links, enables and starts an app's unit.

        Args:
            package (str): The package.

        Returns:
            int: 0 when the unit is running, 1 otherwise.
        """
        app = self._service_app(package)
        if app is None:
            return 1
        try:
            await self._catalog.units.enable(
                app.manifest.service.unit,
                app.manifest.unit_file_path(app.folder),
            )
        except systemd_user_units.UnitError as error:
            self._print(str(error))
            return 1
        self._print(
            f'Enabled and started {app.manifest.service.unit}; it now starts at every login.'
        )
        return 0

    async def disable(self, package: str) -> int:
        """Stops an app's unit and stops it starting at login.

        Args:
            package (str): The package.

        Returns:
            int: 0 when done, 1 otherwise.
        """
        app = self._service_app(package)
        if app is None:
            return 1
        try:
            await self._catalog.units.disable(app.manifest.service.unit)
        except systemd_user_units.UnitError as error:
            self._print(str(error))
            return 1
        self._print(f'Stopped and disabled {app.manifest.service.unit}.')
        return 0

    def _service_app(
        self, package: str
    ) -> app_catalog_module.InstalledApp | None:
        """Finds an app that has a unit, explaining when there is none.

        Args:
            package (str): The package.

        Returns:
            app_catalog_module.InstalledApp | None: The app, or None after printing why.
        """
        app = self._catalog.find(package)
        if app is None:
            self._print(f'No installed package named {package} has an app.')
            return None
        if app.manifest is None:
            self._print(f"Cannot read {package}'s app.toml: {app.error}")
            return None
        if app.manifest.service is None:
            self._print(
                f"{package}'s app names no systemd unit, so there is nothing to enable."
            )
            return None
        return app

    def _print(self, line: str) -> None:
        """Prints one line.

        Args:
            line (str): The line.
        """
        print(line, file=self._output)
