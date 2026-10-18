"""Routes for the phones that receive push notifications.

  GET    /api/devices                    whether push is on, and the registered phones
  POST   /api/devices                    register this phone's Firebase token
  DELETE /api/devices/{device_id}        remove a phone
  POST   /api/devices/{device_id}/test   send a test notification to a phone

The Firebase tokens themselves are never sent back, only the phones' ids and names.

Typical usage example:

  application.include_router(DeviceRoutes(guard, store, channel, problem).router())
"""

import dataclasses
from typing import Any

import fastapi
import pydantic

from trading_agent.devices import device_store as device_store_module
from trading_agent.devices import push_channel as push_channel_module
from trading_agent.gateway import access_guard
from trading_agent.gateway.routes import route_group


class DeviceRegistration(pydantic.BaseModel):
    """What the app sends to register a phone.

    Attributes:
        token: The phone's Firebase Cloud Messaging token.
        name: The phone's name, such as "Samsung SM-M536B".
    """

    token: str = pydantic.Field(min_length=1, max_length=4096)
    name: str = pydantic.Field(default='Android phone', max_length=200)


class DeviceRoutes(route_group.RouteGroup):
    """The device routes."""

    def __init__(
        self,
        guard: access_guard.AccessGuard,
        store: device_store_module.DeviceStore,
        channel: push_channel_module.PushChannel | None,
        problem: str,
    ):
        """Creates the routes.

        Args:
            guard (access_guard.AccessGuard): Checks the access token.
            store (device_store_module.DeviceStore): The registered phones.
            channel (push_channel_module.PushChannel | None): The running push channel, or None when push is off.
            problem (str): Why push is off, or an empty string when it is on.
        """
        super().__init__(guard)
        self._store = store
        self._channel = channel
        self._problem = problem

    def _add_routes(self, router: fastapi.APIRouter) -> None:
        """Adds the device routes.

        Args:
            router (fastapi.APIRouter): The router.
        """
        router.add_api_route('/api/devices', self.devices, methods=['GET'])
        router.add_api_route('/api/devices', self.register, methods=['POST'])
        router.add_api_route(
            '/api/devices/{device_id}', self.remove, methods=['DELETE']
        )
        router.add_api_route(
            '/api/devices/{device_id}/test', self.test, methods=['POST']
        )

    def devices(self) -> dict[str, Any]:
        """Whether push is on, and the registered phones.

        Returns:
            dict[str, Any]: "enabled", "problem" and "devices", each phone without its token.
        """
        phones = []
        for device in self._store.devices():
            phones.append(self._public(device))
        return {
            'enabled': self._channel is not None,
            'problem': self._problem,
            'devices': phones,
        }

    def register(self, registration: DeviceRegistration) -> dict[str, Any]:
        """Registers a phone, or renames it when its token is known.

        Args:
            registration (DeviceRegistration): The phone's token and name.

        Returns:
            dict[str, Any]: The phone, without its token.

        Raises:
            fastapi.HTTPException: The store is full (status 409).
        """
        try:
            device = self._store.register(registration.token, registration.name)
        except device_store_module.DeviceError as error:
            raise fastapi.HTTPException(
                status_code=409, detail=str(error)
            ) from error
        return self._public(device)

    def remove(self, device_id: str) -> dict[str, Any]:
        """Removes a phone.

        Args:
            device_id (str): The phone's id.

        Returns:
            dict[str, Any]: The phone that was removed, without its token.

        Raises:
            fastapi.HTTPException: No phone has that id (status 404).
        """
        try:
            device = self._store.remove(device_id)
        except device_store_module.DeviceError as error:
            raise fastapi.HTTPException(
                status_code=404, detail=str(error)
            ) from error
        return self._public(device)

    async def test(self, device_id: str) -> dict[str, Any]:
        """Sends a test notification to one phone.

        Args:
            device_id (str): The phone.

        Returns:
            dict[str, Any]: "sent", whether Firebase accepted the notification.

        Raises:
            fastapi.HTTPException: Push is off (status 409), or no phone has that id (status 404).
        """
        if self._channel is None:
            raise fastapi.HTTPException(
                status_code=409,
                detail=self._problem or 'Push notifications are off',
            )
        chosen = None
        for device in self._store.devices():
            if device.device_id == device_id:
                chosen = device
        if chosen is None:
            raise fastapi.HTTPException(
                status_code=404,
                detail=f'No phone with id {device_id!r} is registered',
            )
        sent = await self._channel.push_to(
            chosen,
            'Trading Agent',
            'Test notification: push notifications reach this phone.',
            {
                'desk': '',
                'kind': 'test',
            },
        )
        return {
            'sent': sent,
        }

    @staticmethod
    def _public(device: device_store_module.PhoneDevice) -> dict[str, Any]:
        """A phone as the API shows it, without its token.

        Args:
            device (device_store_module.PhoneDevice): The phone.

        Returns:
            dict[str, Any]: Its id, name and registration time.
        """
        shown = dataclasses.asdict(device)
        del shown['token']
        return shown
