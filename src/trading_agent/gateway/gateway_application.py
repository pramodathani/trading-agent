"""Builds the gateway's FastAPI application and runs the traders inside it.

The traders' loops are started when the web server starts and cancelled when it stops, so the gateway is one process that owns every trader.

Typical usage example:

  gateway = GatewayApplication(event_bus, traders, guard)
  uvicorn.run(gateway.build(), host='127.0.0.1', port=8120)
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator, Mapping, Sequence
from pathlib import Path
from typing import Protocol

import fastapi
from fastapi.middleware import cors

from trading_agent.gateway import access_guard
from trading_agent.gateway.routes import event_routes
from trading_agent.gateway.routes import frontend_routes
from trading_agent.gateway.routes import health_routes
from trading_agent.gateway.routes import route_group
from trading_agent.gateway.routes import trader_routes
from trading_agent.gateway.routes import webhook_routes
from trading_agent.journal import secret_redactor
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trader_runtime


class BackgroundWorker(Protocol):
    """Anything with a run coroutine that loops until it is cancelled."""

    async def run(self) -> None:
        """Runs until cancelled."""


class GatewayApplication:
    """The gateway: its web routes and the traders it runs."""

    def __init__(
        self,
        event_bus: event_bus_module.EventBus,
        traders: Mapping[str, trader_runtime.TraderRuntime],
        guard: access_guard.AccessGuard,
        background_workers: Sequence[BackgroundWorker] = (),
        redactor: secret_redactor.SecretRedactor | None = None,
        webhook_token: str = '',
        route_groups: Sequence[route_group.RouteGroup] = (),
        frontend_directory: Path | None = None,
        allowed_origins: Sequence[str] = (),
    ):
        """Creates the gateway without starting anything.

        Args:
            event_bus (event_bus_module.EventBus): The bus every component publishes on.
            traders (Mapping[str, trader_runtime.TraderRuntime]): The traders to run, keyed by name.
            guard (access_guard.AccessGuard): The guard that checks the access token.
            background_workers (Sequence[BackgroundWorker]): Other loops to run beside the traders, such as the trade journal.
            redactor (secret_redactor.SecretRedactor | None): Masks secrets in the live event stream, or None to send events unchanged.
            webhook_token (str): The token incoming webhooks must present, or an empty string to switch them off.
            route_groups (Sequence[route_group.RouteGroup]): The API's route groups; when empty, only the basic trader routes are offered.
            frontend_directory (Path | None): The built web page to serve at every other address, or None to serve no page.
            allowed_origins (Sequence[str]): The other web origins whose pages may call the API, such as the Android app's "https://localhost"; empty allows none.
        """
        self._event_bus = event_bus
        self._traders = traders
        self._guard = guard
        self._background_workers = list(background_workers)
        self._redactor = redactor
        self._webhook_token = webhook_token
        self._route_groups = list(route_groups)
        self._frontend_directory = frontend_directory
        self._allowed_origins = list(allowed_origins)

    def build(self) -> fastapi.FastAPI:
        """Builds the FastAPI application with every route.

        Returns:
            fastapi.FastAPI: The application, ready for uvicorn.
        """
        application = fastapi.FastAPI(
            title='trading-agent gateway',
            lifespan=self._lifespan,
        )
        if self._allowed_origins:
            application.add_middleware(
                cors.CORSMiddleware,
                allow_origins=self._allowed_origins,
                allow_methods=[
                    'GET',
                    'POST',
                    'PUT',
                    'PATCH',
                    'DELETE',
                ],
                allow_headers=[
                    'Authorization',
                    'Content-Type',
                ],
                allow_credentials=False,
            )
        application.include_router(
            health_routes.HealthRoutes(self._traders).router()
        )
        application.include_router(
            webhook_routes.WebhookRoutes(
                self._traders,
                self._webhook_token,
            ).router()
        )
        route_groups = self._route_groups
        if not route_groups:
            route_groups = [
                trader_routes.TraderRoutes(self._traders, self._guard),
            ]
        for group in route_groups:
            application.include_router(group.router())
        application.include_router(
            event_routes.EventRoutes(
                self._event_bus,
                self._guard,
                self._redactor,
            ).router()
        )
        if self._frontend_directory is not None:
            application.include_router(
                frontend_routes.FrontendRoutes(
                    self._frontend_directory
                ).router()
            )
        return application

    @contextlib.asynccontextmanager
    async def _lifespan(
        self,
        application: fastapi.FastAPI,
    ) -> AsyncIterator[None]:
        """Starts every trader's loop, and cancels them when the server stops.

        Args:
            application (fastapi.FastAPI): The application being started.

        Yields:
            None: Control passes back to the server while it runs.
        """
        del application
        trader_tasks = []
        for worker in self._background_workers:
            trader_tasks.append(asyncio.create_task(worker.run()))
        for trader in self._traders.values():
            trader_tasks.append(
                asyncio.create_task(trader.run(), name=f'trader-{trader.name}')
            )
        try:
            yield
        finally:
            for task in trader_tasks:
                task.cancel()
            await asyncio.gather(*trader_tasks, return_exceptions=True)
