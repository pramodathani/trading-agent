"""The WebSocket that streams every event to a client as it happens.

The handler waits for two things at once: the next event, and the client hanging up. Without the second, a closed connection would only be noticed at the next send, and on a quiet bus its subscription would linger.

Typical usage example:

  application.include_router(EventRoutes(event_bus, guard).router())
"""

import asyncio

import fastapi

from trading_agent.gateway import access_guard
from trading_agent.runtime import event_bus as event_bus_module

_POLICY_VIOLATION = 1008
_DISCONNECT_MESSAGE_TYPE = 'websocket.disconnect'


class EventRoutes:
    """Builds the /ws/events WebSocket route."""

    def __init__(
        self,
        event_bus: event_bus_module.EventBus,
        guard: access_guard.AccessGuard,
    ):
        """Creates the route for one event bus.

        Args:
            event_bus (event_bus_module.EventBus): The bus whose events are streamed.
            guard (access_guard.AccessGuard): The guard that checks the access token.
        """
        self._event_bus = event_bus
        self._guard = guard

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
            websocket (fastapi.WebSocket): The client's connection, with the token in its `token` query parameter.
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
    ) -> None:
        """Sends events until the client disconnects.

        Args:
            websocket (fastapi.WebSocket): The client's connection.
            subscription (event_bus_module.EventSubscription): Where the events come from.
            disconnect_task (asyncio.Task): A task that finishes when the client hangs up.
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
            await websocket.send_json(event_task.result().to_json_dictionary())

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
