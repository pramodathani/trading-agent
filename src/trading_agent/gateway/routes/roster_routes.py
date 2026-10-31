"""Routes for creating, retiring and restoring traders, and for their records.

  GET  /api/trader-records             every trader's record, retired ones included, oldest first
  POST /api/traders                    create a trader and start it
  POST /api/traders/{trader}/retire    stop a trader and mark it retired; its files stay
  POST /api/traders/{trader}/restore   bring a retired trader back

The records have their own address because /api/traders/records would be read as a trader named "records".

Typical usage example:

  application.include_router(RosterRoutes(guard, registry).router())
"""

from typing import Any

import fastapi
import pydantic

from trading_agent.configuration import agent_configuration
from trading_agent.gateway import access_guard
from trading_agent.gateway.routes import route_group
from trading_agent.traders import trader_registry as trader_registry_module
from trading_agent.traders import trader_store


class NewTraderRequest(pydantic.BaseModel):
    """The body of a new trader.

    Attributes:
        name: The trader's name.
        mandate: What it will trade and how.
        backend_order: The backends to use, most preferred first, or an empty list for the defaults.
        heartbeat_minutes: Minutes between heartbeats, 0 for no heartbeat, or None for the default.
        scheduled_checks: India times, as HH:MM, when it is woken on trading days.
        introduce: Whether to ask it at once to restate its mandate and propose how it will trade it.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    name: str = pydantic.Field(min_length=1, max_length=200)
    mandate: str = pydantic.Field(min_length=1, max_length=4000)
    backend_order: list[str] = []
    heartbeat_minutes: int | None = pydantic.Field(default=None, ge=0, le=240)
    scheduled_checks: list[str] = []
    introduce: bool = True


class RosterRoutes(route_group.RouteGroup):
    """The routes that change which traders exist."""

    def __init__(
        self,
        guard: access_guard.AccessGuard,
        registry: trader_registry_module.TraderRegistry,
    ):
        """Creates the routes.

        Args:
            guard (access_guard.AccessGuard): Checks the access token.
            registry (trader_registry_module.TraderRegistry): Creates, retires and restores the traders.
        """
        super().__init__(guard)
        self._registry = registry

    def _add_routes(self, router: fastapi.APIRouter) -> None:
        """Adds the roster routes.

        Args:
            router (fastapi.APIRouter): The router.

        Returns:
            None.
        """
        router.add_api_route(
            '/api/trader-records', self.list_records, methods=['GET']
        )
        router.add_api_route(
            '/api/traders',
            self.create,
            methods=['POST'],
            status_code=201,
        )
        router.add_api_route(
            '/api/traders/{trader_name}/retire',
            self.retire,
            methods=['POST'],
        )
        router.add_api_route(
            '/api/traders/{trader_name}/restore',
            self.restore,
            methods=['POST'],
        )

    def list_records(self) -> dict[str, Any]:
        """Every trader's record.

        Returns:
            dict[str, Any]: The records, oldest first, each with whether the trader is running now.

        Raises:
            fastapi.HTTPException: A record cannot be read (status 500).
        """
        running = set(self._registry.names())
        try:
            stored = self._registry.records()
        except trader_store.TraderStoreError as error:
            raise fastapi.HTTPException(
                status_code=500, detail=str(error)
            ) from error
        records = []
        for record in stored:
            entry = self._record_document(record)
            entry['running'] = record.name in running
            records.append(entry)
        return {
            'records': records,
        }

    async def create(self, request: NewTraderRequest) -> dict[str, Any]:
        """Creates a trader and starts it.

        Args:
            request (NewTraderRequest): The new trader.

        Returns:
            dict[str, Any]: Its record.

        Raises:
            fastapi.HTTPException: The name is invalid or taken, a backend is unknown, or a setting is out of range (status 400).
        """
        try:
            trader = await self._registry.create(
                trader_store.NewTrader(
                    name=request.name,
                    mandate=request.mandate,
                    backend_order=tuple(request.backend_order),
                    heartbeat_minutes=request.heartbeat_minutes,
                    scheduled_checks=tuple(request.scheduled_checks),
                ),
                introduce=request.introduce,
            )
        except trader_store.TraderStoreError as error:
            raise fastapi.HTTPException(
                status_code=400, detail=str(error)
            ) from error
        return self._record_document(self._registry.record(trader.name))

    async def retire(self, trader_name: str) -> dict[str, Any]:
        """Retires a trader.

        Args:
            trader_name (str): The trader.

        Returns:
            dict[str, Any]: Its record, now retired.

        Raises:
            fastapi.HTTPException: There is no such running trader, it is the last one, or it still owns instruments or has open orders (status 400).
        """
        try:
            record = await self._registry.retire(trader_name)
        except trader_store.TraderStoreError as error:
            raise fastapi.HTTPException(
                status_code=400, detail=str(error)
            ) from error
        return self._record_document(record)

    async def restore(self, trader_name: str) -> dict[str, Any]:
        """Brings a retired trader back.

        Args:
            trader_name (str): The trader.

        Returns:
            dict[str, Any]: Its record.

        Raises:
            fastapi.HTTPException: There is no such retired trader (status 400).
        """
        try:
            await self._registry.restore(trader_name)
        except trader_store.TraderStoreError as error:
            raise fastapi.HTTPException(
                status_code=400, detail=str(error)
            ) from error
        return self._record_document(self._registry.record(trader_name))

    def _record_document(
        self, record: agent_configuration.TraderConfiguration
    ) -> dict[str, Any]:
        """Turns a record into the JSON the routes answer with.

        Args:
            record (agent_configuration.TraderConfiguration): The record.

        Returns:
            dict[str, Any]: Its name, mandate, creation time, retirement, models and schedule.
        """
        return {
            'name': record.name,
            'mandate': record.mandate,
            'created_at': record.created_at,
            'retired': record.retired,
            'backend_order': list(record.backend_order),
            'heartbeat_minutes': record.heartbeat_minutes,
            'rollover_time': record.rollover_time,
            'scheduled_checks': list(record.scheduled_checks),
        }
