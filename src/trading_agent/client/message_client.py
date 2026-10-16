"""Sends one message to a running gateway and prints the reply as it streams in.

It is what `trading-agent send` uses, so a desk can be talked to from the terminal, or with `!` from Claude Code, before the web interface exists.

Typical usage example:

  client = MessageClient('http://127.0.0.1:8120', token)
  exit_code = asyncio.run(client.send('main', 'What time is it?'))
"""

import asyncio
import json
import sys
from typing import Any, TextIO

import httpx
import websockets

_REPLY_TIMEOUT_SECONDS = 600.0


class MessageClient:
    """A small client for the gateway's message route and event stream."""

    def __init__(
        self,
        base_url: str,
        access_token: str,
        output: TextIO = sys.stdout,
    ):
        """Creates the client.

        Args:
            base_url (str): The gateway's address, such as http://127.0.0.1:8120.
            access_token (str): The gateway's access token.
            output (TextIO): Where the reply is printed.
        """
        self._base_url = base_url.rstrip('/')
        self._access_token = access_token
        self._output = output

    async def send(self, desk_name: str, text: str) -> int:
        """Sends the message and prints everything the desk does until its turn ends.

        Args:
            desk_name (str): The desk to talk to.
            text (str): The message, or a /command.

        Returns:
            int: 0 when the turn finished normally, 1 when it ended in an error.
        """
        events_address = (
            self._base_url.replace('http', 'ws', 1)
            + f'/ws/events?token={self._access_token}'
        )
        async with websockets.connect(events_address) as socket:
            async with httpx.AsyncClient() as http_client:
                response = await http_client.post(
                    f'{self._base_url}/api/desks/{desk_name}/messages',
                    headers={
                        'Authorization': f'Bearer {self._access_token}',
                    },
                    json={
                        'text': text,
                    },
                )
            if response.status_code != 202:
                self._print(
                    f'The gateway refused the message: HTTP {response.status_code} {response.text}'
                )
                return 1
            trigger_id = response.json()['trigger_id']
            return await asyncio.wait_for(
                self._follow(socket, trigger_id),
                timeout=_REPLY_TIMEOUT_SECONDS,
            )

    async def _follow(self, socket: Any, trigger_id: str) -> int:
        """Prints the events of one trigger until its turn finishes.

        Args:
            socket (Any): The open event stream.
            trigger_id (str): The trigger whose events to print.

        Returns:
            int: 0 for a normal finish, 1 when the turn ended in an error.
        """
        exit_code = 0
        streamed_any_text = False
        while True:
            event = json.loads(await socket.recv())
            payload = event['payload']
            if payload.get('trigger_id') != trigger_id:
                continue
            kind = event['kind']
            if kind == 'text_delta':
                self._output.write(payload['text'])
                self._output.flush()
                streamed_any_text = True
            elif kind == 'tool_call':
                self._print(
                    f'\n  [tool] {payload["name"]}({json.dumps(payload["arguments"])[:200]})'
                )
            elif kind == 'backend_unavailable':
                self._print(
                    f'\n  [model] {payload["backend"]} unavailable: {payload["reason"][:200]}'
                )
            elif kind == 'backend_switch':
                self._print(f'\n  [model] answered by {payload["to"]}')
            elif kind == 'text':
                if not streamed_any_text:
                    self._print(payload['text'])
                else:
                    self._print('')
            elif kind == 'error':
                self._print(f'\n  [error] {payload["error"]}')
                exit_code = 1
            elif kind == 'turn_finished':
                return exit_code

    def _print(self, line: str) -> None:
        """Prints one line.

        Args:
            line (str): The line.
        """
        print(line, file=self._output, flush=True)
