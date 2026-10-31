"""Tests for GatewayClient, run against the gateway in the same process."""

import asyncio
from typing import Any

import httpx
import pytest

from trading_agent.configuration import agent_configuration
from trading_agent.gateway import access_guard
from trading_agent.gateway import gateway_application
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import no_model_turn_runner
from trading_agent.runtime import trader_runtime
from trading_agent.terminal import gateway_client

_TOKEN = 'test-token-that-is-long-enough-1234567890'


def _gateway_transport() -> httpx.ASGITransport:
    """Builds a gateway with one trader, reached without the network.

    Returns:
        httpx.ASGITransport: A transport that calls the gateway in this process.
    """
    event_bus = event_bus_module.EventBus()
    traders = {
        'general': trader_runtime.TraderRuntime(
            agent_configuration.TraderConfiguration(name='general'),
            event_bus,
            no_model_turn_runner.NoModelTurnRunner(),
        ),
    }
    application = gateway_application.GatewayApplication(
        event_bus,
        traders,
        access_guard.AccessGuard(_TOKEN),
    ).build()
    return httpx.ASGITransport(app=application)


def _call(token: str, method_name: str, *arguments: Any) -> Any:
    """Calls one GatewayClient method against the in-process gateway.

    Args:
        token (str): The access token to send.
        method_name (str): The method to call.
        *arguments (Any): Its arguments.

    Returns:
        Any: The method's answer.
    """

    async def call() -> Any:
        """Opens the client, calls the method and closes the client.

        Returns:
            Any: The method's answer.
        """
        client = gateway_client.GatewayClient(
            'http://gateway', token, transport=_gateway_transport()
        )
        async with client:
            method = getattr(client, method_name)
            return await method(*arguments)

    return asyncio.run(call())


class TestGatewayClient:
    """Tests for answers and errors."""

    def test_traders(self) -> None:
        """The traders route lists the trader."""
        answer = _call(_TOKEN, 'traders')

        assert answer['traders'][0]['name'] == 'general'

    def test_trader_commands(self) -> None:
        """The commands route lists the built-in commands with how they run."""
        answer = _call(_TOKEN, 'trader_commands', 'general')

        commands = {}
        for entry in answer['commands']:
            commands[entry['usage']] = entry
        assert commands['/status']['runs'] == 'at_once'
        assert commands['/btw <question>']['runs'] == 'beside'
        assert commands['/new']['runs'] == 'queued'
        assert commands['/stop']['runs'] == 'at_once'
        assert '/<skill-name> ...' not in commands

    def test_a_wrong_token_raises(self) -> None:
        """A wrong token is reported with the gateway's explanation."""
        with pytest.raises(gateway_client.GatewayError) as raised:
            _call('wrong', 'traders')

        assert raised.value.status_code == 401
        assert 'access token' in raised.value.message

    def test_an_unknown_trader_raises(self) -> None:
        """An unknown trader is a 404."""
        with pytest.raises(gateway_client.GatewayError) as raised:
            _call(_TOKEN, 'trader_context', 'nobody')

        assert raised.value.status_code == 404

    def test_events_address(self) -> None:
        """The event stream's address carries the token and the trader."""
        client = gateway_client.GatewayClient('http://127.0.0.1:8120', 'a b')

        assert (
            client.events_address('general')
            == 'ws://127.0.0.1:8120/ws/events?token=a+b&trader=general'
        )
        asyncio.run(client.close())
