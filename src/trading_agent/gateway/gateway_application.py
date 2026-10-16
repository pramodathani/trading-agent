"""Builds the gateway's FastAPI application and runs the desks inside it.

The desks' loops are started when the web server starts and cancelled when it stops, so the gateway is one process that owns every desk.

Typical usage example:

  gateway = GatewayApplication(event_bus, desks, guard)
  uvicorn.run(gateway.build(), host='127.0.0.1', port=8120)
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator, Mapping

import fastapi

from trading_agent.gateway import access_guard
from trading_agent.gateway.routes import desk_routes
from trading_agent.gateway.routes import event_routes
from trading_agent.gateway.routes import health_routes
from trading_agent.runtime import desk_runtime
from trading_agent.runtime import event_bus as event_bus_module


class GatewayApplication:
    """The gateway: its web routes and the desks it runs."""

    def __init__(
        self,
        event_bus: event_bus_module.EventBus,
        desks: Mapping[str, desk_runtime.DeskRuntime],
        guard: access_guard.AccessGuard,
    ):
        """Creates the gateway without starting anything.

        Args:
            event_bus (event_bus_module.EventBus): The bus every component publishes on.
            desks (Mapping[str, desk_runtime.DeskRuntime]): The desks to run, keyed by name.
            guard (access_guard.AccessGuard): The guard that checks the access token.
        """
        self._event_bus = event_bus
        self._desks = desks
        self._guard = guard

    def build(self) -> fastapi.FastAPI:
        """Builds the FastAPI application with every route.

        Returns:
            fastapi.FastAPI: The application, ready for uvicorn.
        """
        application = fastapi.FastAPI(
            title='trading-agent gateway',
            lifespan=self._lifespan,
        )
        application.include_router(
            health_routes.HealthRoutes(self._desks).router()
        )
        application.include_router(
            desk_routes.DeskRoutes(self._desks, self._guard).router()
        )
        application.include_router(
            event_routes.EventRoutes(self._event_bus, self._guard).router()
        )
        return application

    @contextlib.asynccontextmanager
    async def _lifespan(
        self,
        application: fastapi.FastAPI,
    ) -> AsyncIterator[None]:
        """Starts every desk's loop, and cancels them when the server stops.

        Args:
            application (fastapi.FastAPI): The application being started.

        Yields:
            None: Control passes back to the server while it runs.
        """
        del application
        desk_tasks = []
        for desk in self._desks.values():
            desk_tasks.append(
                asyncio.create_task(desk.run(), name=f'desk-{desk.name}')
            )
        try:
            yield
        finally:
            for task in desk_tasks:
                task.cancel()
            await asyncio.gather(*desk_tasks, return_exceptions=True)
