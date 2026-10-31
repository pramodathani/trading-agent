"""Tests for the gateway's routes, run in-process with FastAPI's test client."""

import time

import fastapi.testclient
import pytest
import starlette.websockets

from trading_agent.configuration import agent_configuration
from trading_agent.gateway import access_guard
from trading_agent.gateway import gateway_application
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import no_model_turn_runner
from trading_agent.runtime import trader_runtime

_TOKEN = 'test-token-that-is-long-enough-1234567890'


def _client(
    allowed_origins: tuple[str, ...] = (),
) -> fastapi.testclient.TestClient:
    """Builds a gateway with one trader and a test client for it.

    Args:
        allowed_origins (tuple[str, ...]): The other web origins the gateway lets call its API.

    Returns:
        fastapi.testclient.TestClient: A client for the gateway; use it in a with statement so the trader loop runs.
    """
    event_bus = event_bus_module.EventBus()
    traders = {
        'main': trader_runtime.TraderRuntime(
            agent_configuration.TraderConfiguration(name='main'),
            event_bus,
            no_model_turn_runner.NoModelTurnRunner(),
        ),
    }
    gateway = gateway_application.GatewayApplication(
        event_bus,
        traders,
        access_guard.AccessGuard(_TOKEN),
        allowed_origins=allowed_origins,
    )
    return fastapi.testclient.TestClient(gateway.build())


class TestGateway:
    """Tests for the health, trader and event routes."""

    def test_health_needs_no_token(self) -> None:
        """The health route answers without a token and lists the trader."""
        with _client() as client:
            response = client.get('/api/health')

        assert response.status_code == 200
        assert response.json()['traders'][0]['name'] == 'main'

    def test_message_without_token_is_rejected(self) -> None:
        """Sending a message without the token gets HTTP 401."""
        with _client() as client:
            response = client.post(
                '/api/traders/main/messages',
                json={
                    'text': 'hello',
                },
            )

        assert response.status_code == 401

    def test_message_to_unknown_trader_is_404(self) -> None:
        """Sending a message to a trader that does not exist gets HTTP 404."""
        with _client() as client:
            response = client.post(
                '/api/traders/nowhere/messages',
                headers={
                    'Authorization': f'Bearer {_TOKEN}',
                },
                json={
                    'text': 'hello',
                },
            )

        assert response.status_code == 404

    def test_message_reply_arrives_on_event_stream(self) -> None:
        """A message sent over HTTP comes back as a text event on the WebSocket."""
        events_address = f'/ws/events?token={_TOKEN}'
        with (
            _client() as client,
            client.websocket_connect(events_address) as websocket,
        ):
            response = client.post(
                '/api/traders/main/messages',
                headers={
                    'Authorization': f'Bearer {_TOKEN}',
                },
                json={
                    'text': 'hello trader',
                },
            )
            trigger_id = response.json()['trigger_id']
            received_kinds = []
            reply_text = None
            while 'turn_finished' not in received_kinds:
                event = websocket.receive_json()
                received_kinds.append(event['kind'])
                if event['kind'] == 'text':
                    reply_text = event['payload']['text']
                    assert event['payload']['trigger_id'] == trigger_id

        assert response.status_code == 202
        assert received_kinds == [
            'trigger_received',
            'turn_started',
            'text',
            'turn_finished',
        ]
        assert 'hello trader' in reply_text

    def test_event_stream_with_wrong_token_is_closed(self) -> None:
        """A WebSocket with the wrong token is closed before any event is sent."""
        with (
            _client() as client,
            pytest.raises(starlette.websockets.WebSocketDisconnect),
            client.websocket_connect('/ws/events?token=wrong') as websocket,
        ):
            websocket.receive_json()

    def test_closed_event_stream_releases_its_subscription(self) -> None:
        """When a client closes its WebSocket, its subscription is removed even with no events flowing."""
        event_bus = event_bus_module.EventBus()
        gateway = gateway_application.GatewayApplication(
            event_bus,
            {},
            access_guard.AccessGuard(_TOKEN),
        )
        events_address = f'/ws/events?token={_TOKEN}'
        with fastapi.testclient.TestClient(gateway.build()) as client:
            with client.websocket_connect(events_address):
                for _ in range(100):
                    if event_bus.subscriber_count == 1:
                        break
                    time.sleep(0.01)
                assert event_bus.subscriber_count == 1
            for _ in range(100):
                if event_bus.subscriber_count == 0:
                    break
                time.sleep(0.01)

        assert event_bus.subscriber_count == 0

    def test_empty_token_is_refused(self) -> None:
        """An empty access token is refused when the guard is built."""
        with pytest.raises(ValueError, match='is empty'):
            access_guard.AccessGuard('')


class TestAllowedOrigins:
    """Tests for the cross-origin rule that lets the Android app call the API."""

    def test_allowed_origin_is_answered(self) -> None:
        """A preflight request from an allowed origin is approved for the Authorization header."""
        with _client(('https://localhost',)) as client:
            response = client.options(
                '/api/traders',
                headers={
                    'Origin': 'https://localhost',
                    'Access-Control-Request-Method': 'GET',
                    'Access-Control-Request-Headers': 'authorization',
                },
            )

        assert response.status_code == 200
        assert (
            response.headers['access-control-allow-origin']
            == 'https://localhost'
        )
        assert 'access-control-allow-credentials' not in response.headers

    def test_other_origin_gets_no_permission(self) -> None:
        """A request from an origin that is not listed gets no cross-origin header."""
        with _client(('https://localhost',)) as client:
            response = client.get(
                '/api/health',
                headers={
                    'Origin': 'https://example.com',
                },
            )

        assert 'access-control-allow-origin' not in response.headers

    def test_no_origins_means_no_cross_origin_headers(self) -> None:
        """Without allowed origins the gateway adds no cross-origin header at all."""
        with _client() as client:
            response = client.get(
                '/api/health',
                headers={
                    'Origin': 'https://localhost',
                },
            )

        assert 'access-control-allow-origin' not in response.headers
