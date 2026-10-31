"""The open health check route, which needs no access token.

It reveals only that the gateway is running and the state of each trader, so `trading-agent doctor` and systemd checks can call it without the token.

Typical usage example:

  application.include_router(HealthRoutes(traders).router())
"""

from collections.abc import Mapping
from typing import Any

import fastapi

from trading_agent.runtime import trader_runtime


class HealthRoutes:
    """Builds the /api/health route."""

    def __init__(self, traders: Mapping[str, trader_runtime.TraderRuntime]):
        """Creates the routes for a set of traders.

        Args:
            traders (Mapping[str, trader_runtime.TraderRuntime]): The running traders, keyed by name.
        """
        self._traders = traders

    def router(self) -> fastapi.APIRouter:
        """Builds the router holding the health route.

        Returns:
            fastapi.APIRouter: The router.
        """
        router = fastapi.APIRouter()
        router.add_api_route('/api/health', self.health, methods=['GET'])
        return router

    def health(self) -> dict[str, Any]:
        """Reports that the gateway is running, with each trader's state.

        Returns:
            dict[str, Any]: The status and a list of traders with their state and queue length.
        """
        trader_summaries = []
        for trader in self._traders.values():
            trader_summaries.append(
                {
                    'name': trader.name,
                    'state': str(trader.state),
                    'queued': trader.queued_count,
                }
            )
        return {
            'status': 'ok',
            'traders': trader_summaries,
        }
