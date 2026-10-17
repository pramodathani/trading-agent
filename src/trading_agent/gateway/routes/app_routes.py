"""Routes for the packages' web apps.

  GET  /api/apps                    every app with its address, whether it answers and its unit's state
  POST /api/apps/{package}/{action} start, stop or restart an app's systemd unit

Only units named by an installed package's app.toml can be started or stopped here.

Typical usage example:

  application.include_router(AppRoutes(guard, catalog).router())
"""

import asyncio
import dataclasses
from typing import Any

import fastapi

from trading_agent.extensions import app_catalog as app_catalog_module
from trading_agent.extensions import systemd_user_units
from trading_agent.gateway import access_guard
from trading_agent.gateway.routes import route_group


class AppRoutes(route_group.RouteGroup):
    """The app routes."""

    def __init__(
        self,
        guard: access_guard.AccessGuard,
        catalog: app_catalog_module.AppCatalog,
    ):
        """Creates the routes.

        Args:
            guard (access_guard.AccessGuard): Checks the access token.
            catalog (app_catalog_module.AppCatalog): The packages' apps.
        """
        super().__init__(guard)
        self._catalog = catalog

    def _add_routes(self, router: fastapi.APIRouter) -> None:
        """Adds the app routes.

        Args:
            router (fastapi.APIRouter): The router.
        """
        router.add_api_route('/api/apps', self.list_apps, methods=['GET'])
        router.add_api_route(
            '/api/apps/{package}/{action}', self.act, methods=['POST']
        )

    async def list_apps(self) -> dict[str, Any]:
        """Every app and its state, checked all at once.

        Returns:
            dict[str, Any]: The apps.
        """
        apps = self._catalog.apps()
        statuses = await asyncio.gather(
            *[self._catalog.status(app) for app in apps]
        )
        entries = []
        for app, status in zip(apps, statuses, strict=True):
            entries.append(self._entry(app, status))
        return {
            'apps': entries,
        }

    async def act(self, package: str, action: str) -> dict[str, Any]:
        """Starts, stops or restarts an app's unit.

        Args:
            package (str): The package.
            action (str): "start", "stop" or "restart".

        Returns:
            dict[str, Any]: The app and its state afterwards.

        Raises:
            fastapi.HTTPException: No such app (status 404), the app has no unit or the action is unknown (status 400), or systemctl failed (status 502).
        """
        app = self._catalog.find(package)
        if app is None:
            raise fastapi.HTTPException(
                status_code=404,
                detail=f'No installed package named {package} has an app',
            )
        if app.manifest is None or app.manifest.service is None:
            raise fastapi.HTTPException(
                status_code=400, detail=f'{package} names no systemd unit'
            )
        if action not in systemd_user_units.ACTIONS:
            raise fastapi.HTTPException(
                status_code=400, detail='Use start, stop or restart'
            )
        try:
            await self._catalog.units.act(app.manifest.service.unit, action)
        except systemd_user_units.UnitError as error:
            raise fastapi.HTTPException(
                status_code=502, detail=str(error)
            ) from error
        return self._entry(app, await self._catalog.status(app))

    def _entry(
        self,
        app: app_catalog_module.InstalledApp,
        status: app_catalog_module.AppStatus,
    ) -> dict[str, Any]:
        """Describes one app for the web page.

        Args:
            app (app_catalog_module.InstalledApp): The app.
            status (app_catalog_module.AppStatus): Its state.

        Returns:
            dict[str, Any]: Its package, title, description, address, how it opens, unit and state.
        """
        entry = {
            'package': app.package,
            'error': app.error,
            'title': app.package,
            'description': '',
            'url': None,
            'open_in': 'tab',
            'unit': None,
            'healthy': status.healthy,
            'health_detail': status.health_detail,
            'unit_state': dataclasses.asdict(status.unit_state)
            if status.unit_state is not None
            else None,
            'unit_error': status.unit_error,
        }
        if app.manifest is not None:
            entry['title'] = app.manifest.app.title
            entry['description'] = app.manifest.app.description
            entry['url'] = str(app.manifest.app.url)
            entry['open_in'] = app.manifest.app.open_in
            if app.manifest.service is not None:
                entry['unit'] = app.manifest.service.unit
        return entry
