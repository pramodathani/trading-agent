"""Sends one message to a running gateway and prints the reply as it streams in.

It is what `trading-agent send` and `trading-agent -p` use, so a desk can be talked to from a script, a pipe, or with `!` from Claude Code.

When the desk is busy, the gateway hands a plain message to the running turn instead of queueing it. The client then follows that turn until it ends, as the Telegram channel does. Questions, plans and permission requests the desk raises meanwhile are printed with their ids, to be answered in the terminal program or on the web page.

Three output formats are offered, as in `claude -p`:

  text         the reply as it streams, with one line per tool call
  json         one JSON object at the end, with the result, tool calls and backend
  stream-json  every event of the turn as one JSON line, then a final result line

Typical usage example:

  client = MessageClient('http://127.0.0.1:8120', token)
  exit_code = asyncio.run(client.send('general', 'What time is it?'))
"""

import asyncio
import json
import sys
import time
from typing import Any, TextIO

import websockets

from trading_agent.terminal import gateway_client

_REPLY_TIMEOUT_SECONDS = 600.0
_FORMATS = (
    'text',
    'json',
    'stream-json',
)


class MessageClient:
    """A small client for the gateway's message route and event stream."""

    def __init__(
        self,
        base_url: str,
        access_token: str,
        output: TextIO = sys.stdout,
        output_format: str = 'text',
    ):
        """Creates the client.

        Args:
            base_url (str): The gateway's address, such as http://127.0.0.1:8120.
            access_token (str): The gateway's access token.
            output (TextIO): Where the reply is printed.
            output_format (str): "text", "json" or "stream-json".

        Raises:
            ValueError: The output format is not one of the three.
        """
        if output_format not in _FORMATS:
            raise ValueError(f'Unknown output format: {output_format!r}')
        self._base_url = base_url.rstrip('/')
        self._access_token = access_token
        self._output = output
        self._output_format = output_format

    async def send(self, desk_name: str, text: str) -> int:
        """Sends the message and prints everything the desk does until its turn ends.

        Args:
            desk_name (str): The desk to talk to.
            text (str): The message, or a /command.

        Returns:
            int: 0 when the turn finished normally, 1 when it ended in an error or the gateway refused the message.
        """
        gateway = gateway_client.GatewayClient(
            self._base_url, self._access_token
        )
        async with gateway:
            try:
                socket = await websockets.connect(
                    gateway.events_address(desk_name)
                )
            except (OSError, websockets.InvalidStatus) as error:
                self._problem(
                    f'Could not open the event stream at {self._base_url}: {error}. Is the gateway running? Start it with `bin/trading-agent serve` or `systemctl --user start trading-agent`.'
                )
                return 1
            async with socket:
                try:
                    trigger_id = await gateway.send_message(desk_name, text)
                except gateway_client.GatewayError as error:
                    self._problem(f'The gateway refused the message: {error}')
                    return 1
                follower = TurnFollower(
                    desk_name,
                    trigger_id,
                    self._output,
                    self._output_format,
                )
                return await asyncio.wait_for(
                    follower.follow(socket),
                    timeout=_REPLY_TIMEOUT_SECONDS,
                )

    def _problem(self, line: str) -> None:
        """Reports a problem in the chosen format.

        Args:
            line (str): What went wrong.
        """
        if self._output_format == 'text':
            print(line, file=self._output, flush=True)
            return
        print(
            json.dumps(
                {
                    'kind': 'result',
                    'is_error': True,
                    'result': line,
                },
                ensure_ascii=False,
            ),
            file=self._output,
            flush=True,
        )


class TurnFollower:
    """Reads the event stream for one message and prints what its turn does."""

    def __init__(
        self,
        desk_name: str,
        trigger_id: str,
        output: TextIO,
        output_format: str,
    ):
        """Creates the follower.

        Args:
            desk_name (str): The desk the message went to.
            trigger_id (str): The message's trigger id.
            output (TextIO): Where to print.
            output_format (str): "text", "json" or "stream-json".
        """
        self._desk_name = desk_name
        self._trigger_id = trigger_id
        self._followed_id = trigger_id
        self._output = output
        self._output_format = output_format
        self._streamed_any_text = False
        self._started_at = time.monotonic()
        self._answer = ''
        self._error: str | None = None
        self._backend: str | None = None
        self._tool_calls: list[dict[str, Any]] = []
        self._requests: list[dict[str, Any]] = []

    async def follow(self, socket: Any) -> int:
        """Prints the turn's events until it finishes.

        Args:
            socket (Any): The open event stream, with an async recv method that returns JSON text.

        Returns:
            int: 0 for a normal finish, 1 when the turn ended in an error.
        """
        while True:
            event = json.loads(await socket.recv())
            if self.handle(event):
                return self.finish()

    def handle(self, event: dict[str, Any]) -> bool:
        """Takes one event from the stream.

        Args:
            event (dict[str, Any]): The event.

        Returns:
            bool: True when the followed turn has finished.
        """
        kind = event.get('kind', '')
        payload = event.get('payload') or {}
        if kind == 'user_request' and event.get('desk') == self._desk_name:
            self._stream(event)
            self._show_request(payload)
            return False
        event_trigger = payload.get('trigger_id')
        if event_trigger == self._trigger_id and kind == 'trigger_received':
            self._stream(event)
            if isinstance(payload.get('steering_into'), str):
                self._note(
                    'The desk is busy, so your message goes to the running turn at its next tool call.'
                )
            return False
        if event_trigger == self._trigger_id and kind == 'steering':
            self._stream(event)
            if payload.get('delivered') is True:
                self._followed_id = str(payload.get('into_trigger_id'))
                self._note('Your message reached the running turn.')
            else:
                self._note(
                    'The running turn ended first, so your message is the next turn.'
                )
            return False
        if event_trigger != self._followed_id:
            return False
        self._stream(event)
        return self._take(kind, payload)

    def finish(self) -> int:
        """Prints the closing output for the json formats and picks the exit code.

        Returns:
            int: 0 for a normal finish, 1 when the turn ended in an error.
        """
        exit_code = 0
        if self._error is not None:
            exit_code = 1
        if self._output_format == 'text':
            return exit_code
        request_ids = []
        for request in self._requests:
            request_ids.append(request.get('request_id'))
        result = {
            'kind': 'result',
            'desk': self._desk_name,
            'trigger_id': self._trigger_id,
            'answered_in_trigger_id': self._followed_id,
            'is_error': self._error is not None,
            'result': self._answer,
            'error': self._error,
            'backend': self._backend,
            'tool_calls': self._tool_calls,
            'requests': request_ids,
            'duration_seconds': round(time.monotonic() - self._started_at, 1),
        }
        print(
            json.dumps(result, ensure_ascii=False),
            file=self._output,
            flush=True,
        )
        return exit_code

    def _take(self, kind: str, payload: dict[str, Any]) -> bool:
        """Records one event of the followed turn.

        Args:
            kind (str): The event's kind.
            payload (dict[str, Any]): Its payload.

        Returns:
            bool: True when the turn has finished.
        """
        if kind == 'text_delta':
            if self._output_format == 'text':
                self._output.write(payload.get('text', ''))
                self._output.flush()
            self._streamed_any_text = True
        elif kind == 'tool_call':
            self._tool_calls.append(
                {
                    'call_id': payload.get('call_id'),
                    'name': payload.get('name'),
                    'arguments': payload.get('arguments'),
                    'is_error': None,
                }
            )
            arguments = json.dumps(payload.get('arguments'), ensure_ascii=False)
            self._line(f'\n  [tool] {payload.get("name")}({arguments[:200]})')
        elif kind == 'tool_result':
            for call in self._tool_calls:
                if call['call_id'] == payload.get('call_id'):
                    call['is_error'] = payload.get('is_error') is True
        elif kind == 'backend_unavailable':
            reason = str(payload.get('reason', ''))[:200]
            self._line(
                f'\n  [model] {payload.get("backend")} unavailable: {reason}'
            )
        elif kind == 'backend_switch':
            self._backend = payload.get('to')
            self._line(f'\n  [model] answered by {payload.get("to")}')
        elif kind == 'model_usage':
            if payload.get('backend'):
                self._backend = payload.get('backend')
        elif kind == 'text':
            self._answer = str(payload.get('text', ''))
            if self._streamed_any_text:
                self._line('')
            else:
                self._line(self._answer)
        elif kind == 'error':
            self._error = str(payload.get('error', ''))
            self._line(f'\n  [error] {self._error}')
        elif kind == 'stopped':
            self._error = 'The turn was stopped.'
            self._line('\n  [stopped] The turn was stopped.')
        elif kind == 'turn_finished':
            return True
        return False

    def _show_request(self, request: dict[str, Any]) -> None:
        """Prints a question, plan or permission request with how to answer it.

        Args:
            request (dict[str, Any]): The request.
        """
        self._requests.append(request)
        content = request.get('content')
        if not isinstance(content, dict):
            content = {}
        kind = request.get('kind')
        lines = []
        if kind == 'permission':
            arguments = json.dumps(content.get('arguments'), ensure_ascii=False)
            lines.append(
                f'\n  [permission] The desk wants to run {content.get("tool_name")}({arguments[:200]}).'
            )
        elif kind == 'plan':
            lines.append(
                f'\n  [plan] The desk presents a plan: {content.get("title")}'
            )
        else:
            lines.append('\n  [question] The desk asks:')
            questions = content.get('questions')
            if not isinstance(questions, list):
                questions = []
            for question in questions:
                if isinstance(question, dict):
                    lines.append(f'    {question.get("question")}')
        lines.append(
            f'    Answer it in `bin/trading-agent` or on the web page (request {request.get("request_id")}).'
        )
        self._line('\n'.join(lines))

    def _stream(self, event: dict[str, Any]) -> None:
        """Prints an event as one JSON line in the stream-json format.

        Args:
            event (dict[str, Any]): The event.
        """
        if self._output_format != 'stream-json':
            return
        print(
            json.dumps(event, ensure_ascii=False),
            file=self._output,
            flush=True,
        )

    def _note(self, line: str) -> None:
        """Prints a note about the message's progress in the text format.

        Args:
            line (str): The note.
        """
        self._line(f'  [{line}]')

    def _line(self, line: str) -> None:
        """Prints one line in the text format.

        Args:
            line (str): The line.
        """
        if self._output_format != 'text':
            return
        print(line, file=self._output, flush=True)
