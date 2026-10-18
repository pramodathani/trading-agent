"""Tests for the client behind `trading-agent send` and `trading-agent -p`."""

import asyncio
import io
import json
import socket
import threading
import time
from typing import Any

import uvicorn

from trading_agent.client import message_client
from trading_agent.command_line import CommandLine
from trading_agent.configuration import agent_configuration
from trading_agent.gateway import access_guard
from trading_agent.gateway import gateway_application
from trading_agent.runtime import desk_runtime
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import no_model_turn_runner

_TOKEN = 'test-token-that-is-long-enough-1234567890'


def _event(
    event_kind: str, desk: str = 'general', **payload: Any
) -> dict[str, Any]:
    """Makes one event.

    Args:
        event_kind (str): The event's kind.
        desk (str): The event's desk.
        **payload (Any): The event's payload.

    Returns:
        dict[str, Any]: The event.
    """
    return {
        'kind': event_kind,
        'desk': desk,
        'payload': payload,
        'created_at': '2026-10-19T04:30:00+00:00',
    }


class _RunningGateway:
    """A real gateway with one desk that has no model, served on a free port in a thread."""

    def __init__(self):
        """Builds the gateway without starting it."""
        event_bus = event_bus_module.EventBus()
        desks = {
            'general': desk_runtime.DeskRuntime(
                agent_configuration.DeskConfiguration(name='general'),
                event_bus,
                no_model_turn_runner.NoModelTurnRunner(),
            ),
        }
        application = gateway_application.GatewayApplication(
            event_bus,
            desks,
            access_guard.AccessGuard(_TOKEN),
        ).build()
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            self.port = probe.getsockname()[1]
        self._server = uvicorn.Server(
            uvicorn.Config(
                application,
                host='127.0.0.1',
                port=self.port,
                log_level='warning',
            )
        )
        self._thread = threading.Thread(target=self._server.run, daemon=True)

    def start(self) -> None:
        """Starts serving and waits until the server is up."""
        self._thread.start()
        deadline = time.monotonic() + 10
        while not self._server.started and time.monotonic() < deadline:
            time.sleep(0.05)

    def stop(self) -> None:
        """Stops serving."""
        self._server.should_exit = True
        self._thread.join(timeout=10)


class TestTurnFollower:
    """Tests for following one message's turn on the event stream."""

    def test_a_steered_message_follows_the_running_turn(self) -> None:
        """When the message reaches the running turn, the client prints that turn's answer and finishes with it."""
        output = io.StringIO()
        follower = message_client.TurnFollower('general', 't2', output, 'text')
        events = [
            _event('trigger_received', trigger_id='t2', steering_into='t1'),
            _event(
                'steering',
                trigger_id='t2',
                into_trigger_id='t1',
                delivered=True,
            ),
            _event('text', trigger_id='t1', text='Checked TCS too.'),
        ]
        for event in events:
            assert not follower.handle(event)

        assert follower.handle(_event('turn_finished', trigger_id='t1'))
        assert follower.finish() == 0
        printed = output.getvalue()
        assert 'goes to the running turn' in printed
        assert 'reached the running turn' in printed
        assert 'Checked TCS too.' in printed

    def test_an_undelivered_message_waits_for_its_own_turn(self) -> None:
        """When the running turn ends first, the client keeps waiting for the message's own turn."""
        follower = message_client.TurnFollower(
            'general', 't2', io.StringIO(), 'text'
        )
        follower.handle(
            _event(
                'steering',
                trigger_id='t2',
                into_trigger_id='t1',
                delivered=False,
            )
        )

        assert not follower.handle(_event('turn_finished', trigger_id='t1'))
        assert follower.handle(_event('turn_finished', trigger_id='t2'))

    def test_requests_are_printed_with_their_ids(self) -> None:
        """A permission request of the desk is printed with its id; another desk's is not."""
        output = io.StringIO()
        follower = message_client.TurnFollower('general', 't1', output, 'text')
        follower.handle(
            _event(
                'user_request',
                request_id='r1',
                kind='permission',
                content={
                    'tool_name': 'flatten_desk',
                    'arguments': {
                        'reason': 'test',
                    },
                },
            )
        )
        follower.handle(
            _event(
                'user_request',
                desk='scalper',
                request_id='r2',
                kind='question',
                content={},
            )
        )

        printed = output.getvalue()
        assert 'flatten_desk' in printed
        assert 'request r1' in printed
        assert 'r2' not in printed

    def test_json_output_is_one_object(self) -> None:
        """The json format prints nothing until the end, then one result object."""
        output = io.StringIO()
        follower = message_client.TurnFollower('general', 't1', output, 'json')
        follower.handle(
            _event(
                'tool_call',
                trigger_id='t1',
                call_id='c1',
                name='get_quote',
                arguments={},
            )
        )
        follower.handle(
            _event(
                'tool_result',
                trigger_id='t1',
                call_id='c1',
                name='get_quote',
                is_error=True,
            )
        )
        follower.handle(_event('model_usage', trigger_id='t1', backend='qwen'))
        follower.handle(_event('text', trigger_id='t1', text='Done.'))

        assert output.getvalue() == ''

        follower.handle(_event('turn_finished', trigger_id='t1'))
        follower.finish()
        result = json.loads(output.getvalue())
        assert result['result'] == 'Done.'
        assert result['backend'] == 'qwen'
        assert result['tool_calls'][0]['is_error'] is True

    def test_stream_json_prints_every_event(self) -> None:
        """The stream-json format prints each of the turn's events as a line, then the result."""
        output = io.StringIO()
        follower = message_client.TurnFollower(
            'general', 't1', output, 'stream-json'
        )
        follower.handle(_event('turn_started', trigger_id='t1'))
        follower.handle(_event('turn_finished', trigger_id='t1'))
        follower.finish()

        lines = output.getvalue().splitlines()
        assert [json.loads(line)['kind'] for line in lines] == [
            'turn_started',
            'turn_finished',
            'result',
        ]


class TestMessageClient:
    """Tests against a real gateway on a free port."""

    def test_send_prints_the_reply(self) -> None:
        """A message sent to a running gateway comes back as the desk's reply."""
        gateway = _RunningGateway()
        gateway.start()
        try:
            output = io.StringIO()
            client = message_client.MessageClient(
                f'http://127.0.0.1:{gateway.port}', _TOKEN, output
            )
            exit_code = asyncio.run(client.send('general', 'hello'))
        finally:
            gateway.stop()

        assert exit_code == 0
        assert 'No model is connected' in output.getvalue()

    def test_a_gateway_that_is_not_running(self) -> None:
        """When nothing listens, the client says how to start the gateway."""
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        output = io.StringIO()
        client = message_client.MessageClient(
            f'http://127.0.0.1:{port}', _TOKEN, output
        )

        exit_code = asyncio.run(client.send('general', 'hello'))

        assert exit_code == 1
        assert 'bin/trading-agent serve' in output.getvalue()


class TestCommandLine:
    """Tests for the -p options."""

    def test_print_mode(self) -> None:
        """-p without a subcommand chooses the print command."""
        arguments = CommandLine().parse(
            [
                '-p',
                '/status',
                '--desk',
                'scalper',
                '--output-format',
                'json',
            ]
        )

        assert arguments.command == 'print'
        assert arguments.print_text == '/status'
        assert arguments.chosen_desk == 'scalper'
        assert arguments.output_format == 'json'

    def test_bare_command_still_serves(self) -> None:
        """With no subcommand and no -p, the gateway is served."""
        assert CommandLine().parse([]).command == 'serve'
