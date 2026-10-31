"""Routes for the gateway itself: model usage and the configuration.

  GET /api/usage          today's tokens per trader and backend, and the latest rate-limit reports
  GET /api/configuration  trading_agent.toml as the gateway read it, with every known secret masked

Typical usage example:

  application.include_router(SystemRoutes(guard, configuration, usage, redactor, trader_names).router())
"""

import dataclasses
from collections.abc import Collection
from typing import Any

import fastapi

from trading_agent.configuration import agent_configuration
from trading_agent.gateway import access_guard
from trading_agent.gateway.routes import route_group
from trading_agent.journal import secret_redactor
from trading_agent.journal import usage_tracker


class SystemRoutes(route_group.RouteGroup):
    """The usage and configuration routes."""

    def __init__(
        self,
        guard: access_guard.AccessGuard,
        configuration: agent_configuration.AgentConfiguration,
        usage: usage_tracker.UsageTracker,
        redactor: secret_redactor.SecretRedactor,
        trader_names: Collection[str],
    ):
        """Creates the routes.

        Args:
            guard (access_guard.AccessGuard): Checks the access token.
            configuration (agent_configuration.AgentConfiguration): The configuration the gateway runs with.
            usage (usage_tracker.UsageTracker): Today's model usage.
            redactor (secret_redactor.SecretRedactor): Masks secrets in the configuration.
            trader_names (Collection[str]): The running traders. Read afresh on every request, so the gateway passes its live dictionary of traders and a trader created later is included.
        """
        super().__init__(guard)
        self._configuration = configuration
        self._usage = usage
        self._redactor = redactor
        self._trader_names = trader_names

    def _add_routes(self, router: fastapi.APIRouter) -> None:
        """Adds the system routes.

        Args:
            router (fastapi.APIRouter): The router.
        """
        router.add_api_route('/api/usage', self.usage, methods=['GET'])
        router.add_api_route(
            '/api/configuration', self.configuration, methods=['GET']
        )

    def usage(self) -> dict[str, Any]:
        """Today's model usage.

        Returns:
            dict[str, Any]: For each trader, the calls, tokens and cost per backend, and each backend's latest rate-limit report.
        """
        traders = {}
        for trader_name in self._trader_names:
            backends = {}
            for backend_name, counts in self._usage.today(trader_name).items():
                backends[backend_name] = dataclasses.asdict(counts)
            traders[trader_name] = backends
        return {
            'traders': traders,
            'rate_limits': self._usage.rate_limits(),
        }

    def configuration(self) -> dict[str, Any]:
        """The configuration, with secrets masked.

        Returns:
            dict[str, Any]: Every setting of trading_agent.toml, including defaults, as JSON values.
        """
        settings = self._configuration.model_dump(mode='json')
        return self._redactor.redact(settings)
