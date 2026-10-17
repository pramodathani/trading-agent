"""The `trading-agent mcp list` command: connects to every MCP server once and lists its tools.

It runs on its own, without the gateway, so a new server can be checked before the desks use it.

Typical usage example:

  exit_code = asyncio.run(McpCommands(manager).list())
"""

import asyncio
import contextlib
import sys
from typing import TextIO

from trading_agent.extensions import mcp_client_manager

_SETTLE_TIMEOUT_SECONDS = 70.0
_POLL_SECONDS = 0.2


class McpCommands:
    """Checks the MCP servers for the user."""

    def __init__(
        self,
        manager: mcp_client_manager.McpClientManager,
        output: TextIO = sys.stdout,
    ):
        """Creates the commands.

        Args:
            manager (mcp_client_manager.McpClientManager): The connections to check.
            output (TextIO): Where to print.
        """
        self._manager = manager
        self._output = output

    async def list(self) -> int:
        """Connects to every server, waits for each first attempt, and prints the result.

        Returns:
            int: 0 when every server is ready, 1 when one failed or did not answer in time.
        """
        if not self._manager.connections:
            self._print('No MCP servers are configured.')
            return 0
        task = asyncio.create_task(self._manager.run())
        try:
            waited = 0.0
            while (
                not self._manager.settled() and waited < _SETTLE_TIMEOUT_SECONDS
            ):
                await asyncio.sleep(_POLL_SECONDS)
                waited += _POLL_SECONDS
            for line in self._manager.status_lines():
                self._print(line)
            for tool in self._manager.tools():
                self._print(
                    f'  {tool.server}/{tool.name}: {tool.description[:100]}'
                )
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if len(self._manager.tools()) and self._all_ready():
            return 0
        return 1

    def _all_ready(self) -> bool:
        """Says whether every server is ready.

        Returns:
            bool: True when no server failed or is still connecting.
        """
        for connection in self._manager.connections.values():
            if connection.state != 'ready':
                return False
        return True

    def _print(self, text: str) -> None:
        """Prints one line.

        Args:
            text (str): The line.
        """
        print(text, file=self._output)
