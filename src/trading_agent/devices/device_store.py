"""The phones that receive push notifications, kept in one JSON file.

The Android app registers its Firebase Cloud Messaging token after signing in, with the gateway's access token, so only the owner's phones are added. The user can remove a phone on the Settings page. The file sits in workspace/shared, which the desks can read but never write.

Typical usage example:

  store = DeviceStore(layout.phone_devices_file)
  phone = store.register(firebase_token, 'Galaxy M53')
  store.remove(phone.device_id)
"""

import dataclasses
import datetime
import json
import logging
import os
import secrets
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)
_MOST_DEVICES = 10
_LONGEST_NAME = 80


class DeviceError(ValueError):
    """A phone that is not registered, or one more phone than the store keeps."""


@dataclasses.dataclass(frozen=True)
class PhoneDevice:
    """One phone that receives notifications.

    Attributes:
        device_id: A short random id for the phone, used to remove it.
        token: The Firebase Cloud Messaging token that addresses the app on this phone.
        name: The phone's name as the app reports it, such as "Samsung SM-M536B".
        registered_at: When it was first registered, as an ISO 8601 string in UTC.
    """

    device_id: str
    token: str
    name: str
    registered_at: str


class DeviceStore:
    """The registered phones, kept in one JSON file."""

    def __init__(
        self, path: Path, clock: Callable[[], datetime.datetime] | None = None
    ):
        """Creates the store without reading the file.

        Args:
            path (Path): The JSON file.
            clock (Callable[[], datetime.datetime] | None): Returns the current time in UTC; None uses the system clock.
        """
        self._path = path
        self._clock = clock
        self._lock = threading.Lock()

    def register(self, token: str, name: str) -> PhoneDevice:
        """Adds a phone, or renames it when its token is already known.

        Args:
            token (str): The phone's Firebase Cloud Messaging token.
            name (str): The phone's name.

        Returns:
            PhoneDevice: The phone as stored.

        Raises:
            DeviceError: The token is empty, or ten phones are already registered.
        """
        token = token.strip()
        name = name.strip()[:_LONGEST_NAME] or 'Android phone'
        if not token:
            raise DeviceError('A phone needs its Firebase token to register')
        with self._lock:
            devices = self._read()
            for position, device in enumerate(devices):
                if device.token == token:
                    renamed = dataclasses.replace(device, name=name)
                    devices[position] = renamed
                    self._write(devices)
                    return renamed
            if len(devices) >= _MOST_DEVICES:
                raise DeviceError(
                    f'{_MOST_DEVICES} phones are already registered; remove one on the Settings page first'
                )
            device = PhoneDevice(
                device_id=secrets.token_hex(4),
                token=token,
                name=name,
                registered_at=self._now().isoformat(timespec='seconds'),
            )
            devices.append(device)
            self._write(devices)
            return device

    def remove(self, device_id: str) -> PhoneDevice:
        """Removes a phone, so it gets no more notifications.

        Args:
            device_id (str): The phone's id.

        Returns:
            PhoneDevice: The phone that was removed.

        Raises:
            DeviceError: No phone has that id.
        """
        with self._lock:
            devices = self._read()
            for device in devices:
                if device.device_id == device_id:
                    devices.remove(device)
                    self._write(devices)
                    return device
        raise DeviceError(f'No phone with id {device_id!r} is registered')

    def forget_token(self, token: str) -> None:
        """Removes the phone with a token Firebase says is no longer valid, such as after the app was uninstalled.

        Args:
            token (str): The token.
        """
        with self._lock:
            devices = self._read()
            kept = []
            for device in devices:
                if device.token != token:
                    kept.append(device)
            if len(kept) != len(devices):
                self._write(kept)

    def devices(self) -> list[PhoneDevice]:
        """Every registered phone.

        Returns:
            list[PhoneDevice]: The phones, in the order they were registered.
        """
        with self._lock:
            return self._read()

    def _read(self) -> list[PhoneDevice]:
        """Reads the file.

        Returns:
            list[PhoneDevice]: The phones, or an empty list when the file is missing or damaged.
        """
        if not self._path.is_file():
            return []
        try:
            stored: Any = json.loads(self._path.read_text(encoding='utf-8'))
        except ValueError:
            _LOGGER.exception(
                'The phone devices file is damaged; treating it as empty'
            )
            return []
        devices = []
        for entry in stored.get('devices', []):
            devices.append(PhoneDevice(**entry))
        return devices

    def _write(self, devices: list[PhoneDevice]) -> None:
        """Writes the file in one step, so a crash never leaves half a file.

        Args:
            devices (list[PhoneDevice]): The phones.
        """
        entries = []
        for device in devices:
            entries.append(dataclasses.asdict(device))
        self._path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(
            dir=self._path.parent, prefix='.phone_devices.'
        )
        with os.fdopen(handle, 'w', encoding='utf-8') as file:
            json.dump(
                {
                    'devices': entries,
                },
                file,
                indent=2,
            )
        Path(temporary).replace(self._path)

    def _now(self) -> datetime.datetime:
        """The current time.

        Returns:
            datetime.datetime: Now, in UTC.
        """
        if self._clock is not None:
            return self._clock()
        return datetime.datetime.now(datetime.UTC)
