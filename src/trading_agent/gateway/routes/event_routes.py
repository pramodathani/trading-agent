"""The WebSocket that streams every event to a client as it happens.

A client can ask for one trader's events only with `?trader=<name>`; events that belong to no trader, such as account-wide ones, are always sent.

The handler waits for two things at once: the next event, and the client hanging up. Without the second, a closed connection would only be noticed at the next send, and on a quiet bus its subscription would linger.

Typical usage example:

  application.include_router(EventRoutes(event_bus, guard).router())
"""

import asyncio

import fastapi

from trading_agent.gateway import access_guard
from trading_agent.journal import secret_redactor
from trading_agent.runtime import event_bus as event_bus_module

_POLICY_VIOLATION = 1008
_DISCONNECT_MESSAGE_TYPE = 'websocket.disconnect'


class EventRoutes:
    """Builds the /ws/events WebSocket route."""

    def __init__(
        self,
        event_bus: event_bus_module.EventBus,
        guard: access_guard.AccessGuard,
        redactor: secret_redactor.SecretRedactor | None = None,
    ):
        """Creates the route for one event bus.

        Args:
            event_bus (event_bus_module.EventBus): The bus whose events are streamed.
            guard (access_guard.AccessGuard): The guard that checks the access token.
            redactor (secret_redactor.SecretRedactor | None): Masks secrets before an event is sent, or None to send it unchanged.
        """
        self._event_bus = event_bus
        self._guard = guard
        self._redactor = redactor

    def router(self) -> fastapi.APIRouter:
        """Builds the router holding the WebSocket route.

        Returns:
            fastapi.APIRouter: The router.
        """
        router = fastapi.APIRouter()
        router.add_api_websocket_route('/ws/events', self.stream_events)
        return router

    async def stream_events(self, websocket: fastapi.WebSocket) -> None:
        """Sends each event to the client as JSON until it disconnects.

        Args:
            websocket (fastapi.WebSocket): The client's connection, with the token in its `token` query parameter and an optional trader in `trader`.
        """
        if not self._guard.is_valid(websocket.query_params.get('token')):
            await websocket.close(code=_POLICY_VIOLATION)
            return
        await websocket.accept()
        disconnect_task = asyncio.create_task(
            self._wait_for_disconnect(websocket)
        )
        with self._event_bus.subscribe() as subscription:
            try:
                await self._forward_events(
                    websocket,
                    subscription,
                    disconnect_task,
                    websocket.query_params.get('trader'),
                )
            except fastapi.WebSocketDisconnect:
                return
            finally:
                disconnect_task.cancel()

    async def _forward_events(
        self,
        websocket: fastapi.WebSocket,
        subscription: event_bus_module.EventSubscription,
        disconnect_task: asyncio.Task,
        trader_name: str | None,
    ) -> None:
        """Sends events until the client disconnects.

        Args:
            websocket (fastapi.WebSocket): The client's connection.
            subscription (event_bus_module.EventSubscription): Where the events come from.
            disconnect_task (asyncio.Task): A task that finishes when the client hangs up.
            trader_name (str | None): Send only this trader's events and those of no trader, or None for every event.
        """
        while True:
            event_task = asyncio.create_task(subscription.next_event())
            done, _ = await asyncio.wait(
                {
                    event_task,
                    disconnect_task,
                },
                return_when=asyncio.FIRST_COMPLETED,
            )
            if disconnect_task in done:
                event_task.cancel()
                return
            event = event_task.result()
            if trader_name and event.trader and event.trader != trader_name:
                continue
            dictionary = event.to_json_dictionary()
            if self._redactor is not None:
                dictionary = self._redactor.redact(dictionary)
            await websocket.send_json(dictionary)

    async def _wait_for_disconnect(self, websocket: fastapi.WebSocket) -> None:
        """Reads from the client until it sends its disconnect message.

        The client is not expected to send anything else; any other message is ignored.

        Args:
            websocket (fastapi.WebSocket): The client's connection.
        """
        while True:
            message = await websocket.receive()
            if message['type'] == _DISCONNECT_MESSAGE_TYPE:
                return
