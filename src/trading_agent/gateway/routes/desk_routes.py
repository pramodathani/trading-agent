"""Routes for talking to a desk.

Typical usage example:

  application.include_router(DeskRoutes(desks, guard).router())
"""

from collections.abc import Mapping
from typing import Any

import fastapi
import pydantic

from trading_agent.gateway import access_guard
from trading_agent.runtime import desk_runtime
from trading_agent.runtime import trigger as trigger_module


class MessageRequest(pydantic.BaseModel):
    """The body of a message sent to a desk.

    Attributes:
        text: What to tell or ask the desk.
    """

    text: str = pydantic.Field(min_length=1)


class DeskRoutes:
    """Builds the /api/desks routes, which all need the access token."""

    def __init__(
        self,
        desks: Mapping[str, desk_runtime.DeskRuntime],
        guard: access_guard.AccessGuard,
    ):
        """Creates the routes for a set of desks.

        Args:
            desks (Mapping[str, desk_runtime.DeskRuntime]): The running desks, keyed by name.
            guard (access_guard.AccessGuard): The guard that checks the access token.
        """
        self._desks = desks
        self._guard = guard

    def router(self) -> fastapi.APIRouter:
        """Builds the router holding the desk routes.

        Returns:
            fastapi.APIRouter: The router.
        """
        router = fastapi.APIRouter(
            dependencies=[
                fastapi.Depends(self._guard.require_http_token),
            ],
        )
        router.add_api_route(
            '/api/desks/{desk_name}/messages',
            self.send_message,
            methods=['POST'],
            status_code=202,
        )
        return router

    def send_message(
        self,
        desk_name: str,
        message: MessageRequest,
    ) -> dict[str, Any]:
        """Queues a message for a desk and returns at once.

        The reply arrives later as events on /ws/events.

        Args:
            desk_name (str): The desk to send the message to.
            message (MessageRequest): The message.

        Returns:
            dict[str, Any]: The new trigger's identifier, to match it with later events.

        Raises:
            fastapi.HTTPException: No desk has that name (status 404).
        """
        desk = self._desks.get(desk_name)
        if desk is None:
            raise fastapi.HTTPException(
                status_code=404,
                detail=f'No desk named {desk_name!r}',
            )
        trigger = trigger_module.Trigger.now(
            trigger_module.TriggerSource.USER_MESSAGE,
            desk_name,
            message.text,
        )
        desk.submit(trigger)
        return {
            'trigger_id': trigger.trigger_id,
        }
