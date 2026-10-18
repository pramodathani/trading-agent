"""Tests for the phones that receive push notifications and the worker that pushes to them."""

import asyncio
import datetime
from pathlib import Path

import fastapi.testclient
import pydantic
import pytest

from trading_agent.channels import notification_formatter
from trading_agent.configuration import agent_configuration
from trading_agent.devices import device_store
from trading_agent.devices import push_channel
from trading_agent.gateway import access_guard
from trading_agent.gateway import gateway_application
from trading_agent.gateway.routes import device_routes
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module

_TOKEN = 'test-token-that-is-long-enough-1234567890'
_NOW = datetime.datetime(2026, 10, 19, 4, 0, tzinfo=datetime.UTC)


class FakeSender:
    """Records notifications instead of sending them, and answers with a chosen outcome."""

    def __init__(self, outcome: str = 'sent'):
        """Creates the sender.

        Args:
            outcome (str): What every send answers: "sent", "unregistered" or "failed".
        """
        self.outcome = outcome
        self.sent: list[tuple[str, str, str, dict[str, str]]] = []

    async def send(
        self,
        token: str,
        title: str,
        body: str,
        data: dict[str, str],
    ) -> str:
        """Records one notification.

        Args:
            token (str): The phone's token.
            title (str): The title.
            body (str): The text.
            data (dict[str, str]): The values for the app.

        Returns:
            str: The chosen outcome.
        """
        self.sent.append((token, title, body, data))
        return self.outcome


def _store(folder: Path) -> device_store.DeviceStore:
    """Makes a store in a temporary folder with a fixed clock.

    Args:
        folder (Path): The folder.

    Returns:
        device_store.DeviceStore: The store.
    """
    return device_store.DeviceStore(
        folder / 'phone_devices.json', clock=lambda: _NOW
    )


def _channel(
    store: device_store.DeviceStore,
    sender: FakeSender,
    notifications: list[str],
) -> push_channel.PushChannel:
    """Makes a push channel with a fake sender.

    Args:
        store (device_store.DeviceStore): The phones.
        sender (FakeSender): The fake sender.
        notifications (list[str]): The kinds to push.

    Returns:
        push_channel.PushChannel: The channel.
    """
    return push_channel.PushChannel(
        store,
        sender,
        notification_formatter.NotificationFormatter(notifications),
        event_bus_module.EventBus(),
        notifications,
    )


def _fill() -> event_module.Event:
    """A fill event on the scalper desk.

    Returns:
        event_module.Event: The event.
    """
    return event_module.Event.now(
        event_module.EventKind.FILL,
        'scalper',
        {
            'status': 'COMPLETE',
            'transaction_type': 'BUY',
            'quantity': 50,
            'symbol': 'RELIANCE',
            'filled_quantity': 50,
            'average_price': 2912.5,
        },
    )


def _permission_request() -> event_module.Event:
    """A permission request from the scalper desk.

    Returns:
        event_module.Event: The user_request event.
    """
    return event_module.Event.now(
        event_module.EventKind.USER_REQUEST,
        'scalper',
        {
            'request_id': 'request-1',
            'desk': 'scalper',
            'kind': 'permission',
            'content': {
                'tool_name': 'flatten_desk',
                'arguments': {},
            },
            'created_at': _NOW.isoformat(),
            'status': 'pending',
        },
    )


class TestDeviceStore:
    """Tests for the phone list."""

    def test_register_keeps_the_phone(self, tmp_path: Path) -> None:
        """A registered phone is listed with its name and time."""
        store = _store(tmp_path)

        phone = store.register('firebase-token-1', 'Galaxy M53')

        assert store.devices() == [
            phone,
        ]
        assert phone.name == 'Galaxy M53'
        assert phone.registered_at == '2026-10-19T04:00:00+00:00'

    def test_same_token_renames_instead_of_adding(self, tmp_path: Path) -> None:
        """Registering a known token again renames the phone and keeps its id."""
        store = _store(tmp_path)
        first = store.register('firebase-token-1', 'Old name')

        second = store.register('firebase-token-1', 'New name')

        assert second.device_id == first.device_id
        assert [device.name for device in store.devices()] == [
            'New name',
        ]

    def test_empty_token_is_refused(self, tmp_path: Path) -> None:
        """A registration without a token is refused."""
        with pytest.raises(device_store.DeviceError):
            _store(tmp_path).register('  ', 'Galaxy M53')

    def test_remove_and_forget(self, tmp_path: Path) -> None:
        """A phone can be removed by id, and another by its token."""
        store = _store(tmp_path)
        first = store.register('firebase-token-1', 'One')
        store.register('firebase-token-2', 'Two')

        store.remove(first.device_id)
        store.forget_token('firebase-token-2')

        assert store.devices() == []
        with pytest.raises(device_store.DeviceError):
            store.remove(first.device_id)


class TestPushChannel:
    """Tests for the worker that turns events into notifications."""

    def test_fill_is_pushed_with_the_desk_as_title(
        self, tmp_path: Path
    ) -> None:
        """A fill reaches every phone, titled with the desk and carrying it for the tap."""
        store = _store(tmp_path)
        store.register('firebase-token-1', 'Galaxy M53')
        sender = FakeSender()

        asyncio.run(_channel(store, sender, ['fills']).handle(_fill()))

        assert sender.sent == [
            (
                'firebase-token-1',
                'scalper',
                'COMPLETE buy 50 RELIANCE, 50 filled at 2912.5',
                {
                    'desk': 'scalper',
                    'kind': 'fill',
                },
            ),
        ]

    def test_kinds_not_chosen_are_not_pushed(self, tmp_path: Path) -> None:
        """A fill is not pushed when fills are not in the notifications list."""
        store = _store(tmp_path)
        store.register('firebase-token-1', 'Galaxy M53')
        sender = FakeSender()

        asyncio.run(_channel(store, sender, ['halts']).handle(_fill()))

        assert sender.sent == []

    def test_permission_request_is_pushed(self, tmp_path: Path) -> None:
        """A permission request is pushed with the tool's name and the request's id."""
        store = _store(tmp_path)
        store.register('firebase-token-1', 'Galaxy M53')
        sender = FakeSender()

        asyncio.run(
            _channel(store, sender, ['requests']).handle(_permission_request())
        )

        token, title, body, data = sender.sent[0]
        assert token == 'firebase-token-1'
        assert title == 'scalper needs your permission'
        assert 'flatten_desk' in body
        assert data['request_id'] == 'request-1'

    def test_requests_off_means_no_request_push(self, tmp_path: Path) -> None:
        """Without "requests" in the list, permission requests are not pushed."""
        store = _store(tmp_path)
        store.register('firebase-token-1', 'Galaxy M53')
        sender = FakeSender()

        asyncio.run(
            _channel(store, sender, ['fills']).handle(_permission_request())
        )

        assert sender.sent == []

    def test_unregistered_phone_is_forgotten(self, tmp_path: Path) -> None:
        """A phone Firebase no longer knows is removed from the list."""
        store = _store(tmp_path)
        store.register('firebase-token-1', 'Galaxy M53')

        asyncio.run(
            _channel(store, FakeSender('unregistered'), ['fills']).handle(
                _fill()
            )
        )

        assert store.devices() == []


class TestPushConfiguration:
    """Tests for the [push] settings."""

    def test_unknown_notification_is_refused(self) -> None:
        """A misspelt notification name is reported when the file is read."""
        with pytest.raises(pydantic.ValidationError):
            agent_configuration.PushConfiguration(
                notifications=[
                    'fils',
                ]
            )

    def test_push_is_off_by_default(self) -> None:
        """Push stays off until the user switches it on."""
        assert not agent_configuration.PushConfiguration().enabled


def _client(
    store: device_store.DeviceStore,
    channel: push_channel.PushChannel | None,
) -> fastapi.testclient.TestClient:
    """Builds a gateway with only the device routes.

    Args:
        store (device_store.DeviceStore): The phones.
        channel (push_channel.PushChannel | None): The push channel, or None when push is off.

    Returns:
        fastapi.testclient.TestClient: A client for it.
    """
    guard = access_guard.AccessGuard(_TOKEN)
    gateway = gateway_application.GatewayApplication(
        event_bus_module.EventBus(),
        {},
        guard,
        route_groups=[
            device_routes.DeviceRoutes(
                guard,
                store,
                channel,
                '' if channel is not None else 'Push notifications are off.',
            ),
        ],
    )
    return fastapi.testclient.TestClient(gateway.build())


class TestDeviceRoutes:
    """Tests for the /api/devices routes."""

    def test_register_list_and_remove(self, tmp_path: Path) -> None:
        """A phone registers, is listed without its token, and can be removed."""
        headers = {
            'Authorization': f'Bearer {_TOKEN}',
        }
        with _client(_store(tmp_path), None) as client:
            registered = client.post(
                '/api/devices',
                json={
                    'token': 'firebase-token-1',
                    'name': 'Galaxy M53',
                },
                headers=headers,
            ).json()
            listed = client.get('/api/devices', headers=headers).json()
            removed = client.delete(
                f'/api/devices/{registered["device_id"]}', headers=headers
            )

        assert 'token' not in registered
        assert listed['enabled'] is False
        assert listed['devices'][0]['name'] == 'Galaxy M53'
        assert 'token' not in listed['devices'][0]
        assert removed.status_code == 200

    def test_routes_need_the_token(self, tmp_path: Path) -> None:
        """Registering without the access token is refused."""
        with _client(_store(tmp_path), None) as client:
            response = client.post(
                '/api/devices',
                json={
                    'token': 'firebase-token-1',
                },
            )

        assert response.status_code == 401

    def test_test_notification(self, tmp_path: Path) -> None:
        """The test button sends to that phone when push is on, and explains when it is off."""
        headers = {
            'Authorization': f'Bearer {_TOKEN}',
        }
        store = _store(tmp_path)
        phone = store.register('firebase-token-1', 'Galaxy M53')
        sender = FakeSender()
        with _client(store, _channel(store, sender, ['fills'])) as client:
            sent = client.post(
                f'/api/devices/{phone.device_id}/test', headers=headers
            ).json()
        with _client(store, None) as client:
            refused = client.post(
                f'/api/devices/{phone.device_id}/test', headers=headers
            )

        assert sent == {
            'sent': True,
        }
        assert sender.sent[0][0] == 'firebase-token-1'
        assert refused.status_code == 409
