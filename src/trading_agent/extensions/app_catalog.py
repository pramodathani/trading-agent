"""The web apps that installed packages bring, and whether each is up.

An app is up when its page answers, which is checked by asking its health address with a short timeout; any answer below 500 counts, because an app that asks for a login still answers. Its unit's state comes from systemd.

Typical usage example:

  catalog = AppCatalog(packages, SystemdUserUnits())
  for app in catalog.apps():
      status = await catalog.status(app)
"""

import asyncio
import dataclasses
from pathlib import Path

import httpx

from trading_agent.extensions import app_manifest as app_manifest_module
from trading_agent.extensions import (
    installed_packages as installed_packages_module,
)
from trading_agent.extensions import (
    systemd_user_units as systemd_user_units_module,
)

_HEALTH_TIMEOUT_SECONDS = 3.0
_SERVER_ERROR = 500


@dataclasses.dataclass(frozen=True)
class InstalledApp:
    """One package's app.

    Attributes:
        package: The package's name, which also names the app in addresses.
        folder: The installed package's folder.
        manifest: The app's settings, or None when app.toml cannot be read.
        error: Why app.toml cannot be read, or an empty string.
    """

    package: str
    folder: Path
    manifest: app_manifest_module.AppManifest | None
    error: str


@dataclasses.dataclass(frozen=True)
class AppStatus:
    """Whether one app is up.

    Attributes:
        healthy: Whether its page answered.
        health_detail: The answer's status code, or why there was none.
        unit_state: Its unit's state, or None when it has no unit or systemd could not be asked.
        unit_error: Why systemd could not be asked, or an empty string.
    """

    healthy: bool
    health_detail: str
    unit_state: systemd_user_units_module.UnitState | None
    unit_error: str


class AppCatalog:
    """Finds the apps of installed packages and checks them."""

    def __init__(
        self,
        packages: installed_packages_module.InstalledPackages,
        units: systemd_user_units_module.SystemdUserUnits,
    ):
        """Creates the catalog.

        Args:
            packages (installed_packages_module.InstalledPackages): The installed packages.
            units (systemd_user_units_module.SystemdUserUnits): Talks to systemd.
        """
        self._packages = packages
        self.units = units
        self._reader = app_manifest_module.AppManifestReader()

    def apps(self) -> list[InstalledApp]:
        """Every installed package that has an app.toml, read afresh.

        Returns:
            list[InstalledApp]: The apps, in package-name order.
        """
        apps = []
        for folder in self._packages.folders():
            path = folder / app_manifest_module.APP_FILE_NAME
            if not path.is_file():
                continue
            try:
                manifest = self._reader.read(path)
            except app_manifest_module.AppManifestError as error:
                apps.append(InstalledApp(folder.name, folder, None, str(error)))
                continue
            apps.append(InstalledApp(folder.name, folder, manifest, ''))
        return apps

    def find(self, package: str) -> InstalledApp | None:
        """Finds one package's app.

        Args:
            package (str): The package's name.

        Returns:
            InstalledApp | None: The app, or None when that package has none.
        """
        for app in self.apps():
            if app.package == package:
                return app
        return None

    async def status(self, app: InstalledApp) -> AppStatus:
        """Checks whether an app's page answers and asks systemd about its unit, both at once.

        Args:
            app (InstalledApp): The app.

        Returns:
            AppStatus: The app's state.
        """
        if app.manifest is None:
            return AppStatus(False, app.error, None, '')
        health, unit = await asyncio.gather(
            self._check_health(app.manifest.health_address()),
            self._unit_state(app.manifest),
        )
        healthy, detail = health
        unit_state, unit_error = unit
        return AppStatus(healthy, detail, unit_state, unit_error)

    async def _check_health(self, address: str) -> tuple[bool, str]:
        """Asks the app's health address.

        Args:
            address (str): The address.

        Returns:
            tuple[bool, str]: Whether it answered below 500, and the status code or the kind of failure.
        """
        try:
            async with httpx.AsyncClient(
                timeout=_HEALTH_TIMEOUT_SECONDS
            ) as client:
                response = await client.get(address)
        except httpx.HTTPError as error:
            return False, type(error).__name__
        return (
            response.status_code < _SERVER_ERROR,
            f'status {response.status_code}',
        )

    async def _unit_state(
        self,
        manifest: app_manifest_module.AppManifest,
    ) -> tuple[systemd_user_units_module.UnitState | None, str]:
        """Asks systemd about the app's unit.

        Args:
            manifest (app_manifest_module.AppManifest): The app's settings.

        Returns:
            tuple[systemd_user_units_module.UnitState | None, str]: The state, or None with the reason.
        """
        if manifest.service is None:
            return None, ''
        try:
            return await self.units.state(manifest.service.unit), ''
        except systemd_user_units_module.UnitError as error:
            return None, str(error)
