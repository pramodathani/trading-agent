"""Tests for packages that bring web apps."""

import asyncio
from pathlib import Path

import fastapi
import fastapi.testclient
import pytest

from trading_agent.extensions import app_catalog
from trading_agent.extensions import app_manifest
from trading_agent.extensions import installed_packages
from trading_agent.extensions import package_installer
from trading_agent.extensions import systemd_user_units
from trading_agent.gateway import access_guard
from trading_agent.gateway.routes import app_routes

_TOKEN = 'test-token-that-is-long-enough-1234567890'
_APP_TOML = """[app]
title = "Sridhara"
description = "A trading terminal."
url = "http://127.0.0.1:9/"

[service]
unit = "sridhara.service"
unit_file = "services/sridhara.service"
"""


class _StandInUnits(systemd_user_units.SystemdUserUnits):
    """systemd, as a dictionary of unit states, recording each action.

    Attributes:
        actions: Each (unit, action) asked for.
    """

    def __init__(self):
        """Starts with sridhara running."""
        self.actions: list[tuple[str, str]] = []
        self._active = True

    async def state(self, unit: str) -> systemd_user_units.UnitState:
        """Gives the unit's state.

        Args:
            unit (str): The unit.

        Returns:
            systemd_user_units.UnitState: Active or inactive.
        """
        self._check(unit)
        if self._active:
            return systemd_user_units.UnitState('loaded', 'active', 'running')
        return systemd_user_units.UnitState('loaded', 'inactive', 'dead')

    async def act(self, unit: str, action: str) -> None:
        """Records the action and changes the state.

        Args:
            unit (str): The unit.
            action (str): The action.
        """
        self._check(unit)
        self.actions.append((unit, action))
        self._active = action != 'stop'


def _package(directory: Path, app_toml: str = _APP_TOML) -> Path:
    """Writes a package folder with an app.toml.

    Args:
        directory (Path): Where to write it.
        app_toml (str): The app.toml text.

    Returns:
        Path: The package folder.
    """
    folder = directory / 'source' / 'sridhara'
    folder.mkdir(parents=True)
    (folder / 'app.toml').write_text(app_toml, encoding='utf-8')
    return folder


def _catalog(
    directory: Path, units: systemd_user_units.SystemdUserUnits
) -> app_catalog.AppCatalog:
    """Installs the package and builds a catalog over it.

    Args:
        directory (Path): A scratch folder.
        units (systemd_user_units.SystemdUserUnits): The systemd to use.

    Returns:
        app_catalog.AppCatalog: The catalog.
    """
    packages = installed_packages.InstalledPackages(directory / 'packages')
    package_installer.PackageInstaller(packages).install(
        str(_package(directory)), replace=False
    )
    return app_catalog.AppCatalog(packages, units)


class TestAppManifest:
    """Tests for reading app.toml."""

    def test_unit_file_is_found_inside_the_package(
        self, tmp_path: Path
    ) -> None:
        """A relative unit file is inside the package, and the health address defaults to the url."""
        manifest = app_manifest.AppManifestReader().read(
            _package(tmp_path) / 'app.toml'
        )

        assert manifest.unit_file_path(Path('/packages/sridhara')) == Path(
            '/packages/sridhara/services/sridhara.service'
        )
        assert manifest.health_address() == 'http://127.0.0.1:9/'

    def test_unit_name_must_be_a_service(self, tmp_path: Path) -> None:
        """A unit name that could be read as a systemctl option is refused."""
        bad = _APP_TOML.replace('unit = "sridhara.service"', 'unit = "--now"')

        with pytest.raises(app_manifest.AppManifestError, match='service.unit'):
            app_manifest.AppManifestReader().read(
                _package(tmp_path, bad) / 'app.toml'
            )

    def test_url_must_be_a_web_address(self, tmp_path: Path) -> None:
        """A url that is not http or https is refused."""
        bad = _APP_TOML.replace('http://127.0.0.1:9/', 'file:///etc/passwd')

        with pytest.raises(app_manifest.AppManifestError, match='app.url'):
            app_manifest.AppManifestReader().read(
                _package(tmp_path, bad) / 'app.toml'
            )

    def test_installer_refuses_an_invalid_app(self, tmp_path: Path) -> None:
        """A package whose app.toml is invalid is not installed."""
        packages = installed_packages.InstalledPackages(tmp_path / 'packages')
        bad = _package(tmp_path, '[app]\ntitle = "No address"\n')

        with pytest.raises(package_installer.PackageError):
            package_installer.PackageInstaller(packages).install(
                str(bad), replace=False
            )

        assert not (tmp_path / 'packages' / 'sridhara').exists()


class TestAppCatalog:
    """Tests for listing and checking apps."""

    def test_app_that_does_not_answer_is_not_healthy(
        self, tmp_path: Path
    ) -> None:
        """An app whose page does not answer is reported down, with its unit's state."""
        catalog = _catalog(tmp_path, _StandInUnits())

        app = catalog.find('sridhara')
        status = asyncio.run(catalog.status(app))

        assert app.manifest.app.title == 'Sridhara'
        assert status.healthy is False
        assert status.unit_state.active_state == 'active'

    def test_unit_names_are_checked_before_systemctl(self) -> None:
        """A unit name with spaces or options never reaches systemctl."""
        units = systemd_user_units.SystemdUserUnits()

        with pytest.raises(systemd_user_units.UnitError):
            asyncio.run(units.act('--user poweroff.service', 'start'))
        with pytest.raises(systemd_user_units.UnitError):
            asyncio.run(units.act('sridhara.service', 'mask'))


class TestAppRoutes:
    """Tests for the app routes."""

    def test_list_and_stop(self, tmp_path: Path) -> None:
        """The apps are listed, and stopping one changes its unit's state."""
        units = _StandInUnits()
        group = app_routes.AppRoutes(
            access_guard.AccessGuard(_TOKEN), _catalog(tmp_path, units)
        )
        application = fastapi.FastAPI()
        application.include_router(group.router())
        client = fastapi.testclient.TestClient(application)
        headers = {
            'Authorization': f'Bearer {_TOKEN}',
        }

        listing = client.get('/api/apps', headers=headers)
        stopped = client.post('/api/apps/sridhara/stop', headers=headers)
        unknown_action = client.post('/api/apps/sridhara/mask', headers=headers)
        unknown_app = client.post('/api/apps/nothing/start', headers=headers)

        assert listing.json()['apps'][0]['unit'] == 'sridhara.service'
        assert stopped.json()['unit_state']['active_state'] == 'inactive'
        assert units.actions == [
            (
                'sridhara.service',
                'stop',
            ),
        ]
        assert unknown_action.status_code == 400
        assert unknown_app.status_code == 404
