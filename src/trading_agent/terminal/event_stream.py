"""Keeps the gateway's event stream open, reconnecting after a drop, as the web page's eventSocket.ts does.

Each event is a JSON object with kind, trader, payload and created_at. The stream never replays old events, so a client reads today's history from the journal routes.

Typical usage example:

  stream = EventStream(gateway.events_address())
  await stream.follow(on_event, on_state)
"""

import asyncio
import json
from collections.abc import Callable
from typing import Any

import websockets

_FIRST_WAIT_SECONDS = 1.0
_LONGEST_WAIT_SECONDS = 15.0
_POLICY_VIOLATION = 1008

LIVE = 'live'
CONNECTING = 'connecting'
RECONNECTING = 'reconnecting'
REFUSED = 'refused'


class AccessRefusedError(Exception):
    """The gateway closed the event stream because the access token is wrong."""


class EventStream:
    """One client's view of the gateway's events."""

    def __init__(
        self,
        address: str,
        connect: Callable[[str], Any] = websockets.connect,
    ):
        """Creates the stream without connecting.

        Args:
            address (str): The WebSocket address, with the token, from GatewayClient.events_address.
            connect (Callable[[str], Any]): Opens a connection; replaced by a stand-in in tests.
        """
        self._address = address
        self._connect = connect

    async def follow(
        self,
        on_event: Callable[[dict[str, Any]], None],
        on_state: Callable[[str], None],
    ) -> None:
        """Passes every event to on_event until cancelled, reconnecting after a drop.

        The wait before reconnecting doubles from 1 second up to 15 seconds, and starts again at 1 second after a connection that worked.

        Args:
            on_event (Callable[[dict[str, Any]], None]): Called with each event.
            on_state (Callable[[str], None]): Called with "connecting", "live", "reconnecting" or "refused".

        Raises:
            AccessRefusedError: The gateway refused the access token.
        """
        wait_seconds = _FIRST_WAIT_SECONDS
        on_state(CONNECTING)
        while True:
            try:
                async with self._connect(self._address) as socket:
                    on_state(LIVE)
                    wait_seconds = _FIRST_WAIT_SECONDS
                    async for message in socket:
                        on_event(json.loads(message))
            except websockets.ConnectionClosed as closed:
                if self._was_refused(closed):
                    on_state(REFUSED)
                    raise AccessRefusedError(
                        'The gateway refused the access token'
                    ) from closed
            except websockets.InvalidStatus as refused:
                if refused.response.status_code in (401, 403):
                    on_state(REFUSED)
                    raise AccessRefusedError(
                        'The gateway refused the access token'
                    ) from refused
            except OSError:
                pass
            on_state(RECONNECTING)
            await asyncio.sleep(wait_seconds)
            wait_seconds = min(wait_seconds * 2, _LONGEST_WAIT_SECONDS)

    def _was_refused(self, closed: websockets.ConnectionClosed) -> bool:
        """Says whether the gateway closed the stream over the token.

        Args:
            closed (websockets.ConnectionClosed): How the connection ended.

        Returns:
            bool: True when the close code is 1008, policy violation.
        """
        if closed.rcvd is None:
            return False
        return closed.rcvd.code == _POLICY_VIOLATION
