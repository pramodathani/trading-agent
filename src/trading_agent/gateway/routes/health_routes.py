"""The open health check route, which needs no access token.

It reveals only that the gateway is running and the state of each desk, so `trading-agent doctor` and systemd checks can call it without the token.

Typical usage example:

  application.include_router(HealthRoutes(desks).router())
"""

from collections.abc import Mapping
from typing import Any

import fastapi

from trading_agent.runtime import desk_runtime


class HealthRoutes:
    """Builds the /api/health route."""

    def __init__(self, desks: Mapping[str, desk_runtime.DeskRuntime]):
        """Creates the routes for a set of desks.

        Args:
            desks (Mapping[str, desk_runtime.DeskRuntime]): The running desks, keyed by name.
        """
        self._desks = desks

    def router(self) -> fastapi.APIRouter:
        """Builds the router holding the health route.

        Returns:
            fastapi.APIRouter: The router.
        """
        router = fastapi.APIRouter()
        router.add_api_route('/api/health', self.health, methods=['GET'])
        return router

    def health(self) -> dict[str, Any]:
        """Reports that the gateway is running, with each desk's state.

        Returns:
            dict[str, Any]: The status and a list of desks with their state and queue length.
        """
        desk_summaries = []
        for desk in self._desks.values():
            desk_summaries.append(
                {
                    'name': desk.name,
                    'state': str(desk.state),
                    'queued': desk.queued_count,
                }
            )
        return {
            'status': 'ok',
            'desks': desk_summaries,
        }
