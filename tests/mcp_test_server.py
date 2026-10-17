"""A tiny MCP server, started over stdio by the MCP tests.

Typical usage example:

  python tests/mcp_test_server.py
"""

import json
import os

from mcp.server.mcpserver import MCPServer


class TestServer:
    """An MCP server with three tools: add, environment and fail."""

    def __init__(self):
        """Creates the server and registers its tools."""
        self._server = MCPServer('trading-agent-test')
        self._server.add_tool(
            self.add,
            name='add',
            description='Adds two whole numbers.',
        )
        self._server.add_tool(
            self.environment,
            name='environment',
            description='Lists the names of the environment variables the server received.',
        )
        self._server.add_tool(
            self.fail,
            name='fail',
            description='Always fails.',
        )

    def add(self, first: int, second: int) -> str:
        """Adds two numbers.

        Args:
            first (int): The first number.
            second (int): The second number.

        Returns:
            str: The sum.
        """
        return str(first + second)

    def environment(self) -> str:
        """Lists the server's environment variable names.

        Returns:
            str: A JSON list of names.
        """
        return json.dumps(sorted(os.environ))

    def fail(self) -> str:
        """Fails on purpose.

        Returns:
            str: Never returns.

        Raises:
            RuntimeError: Always.
        """
        raise RuntimeError('this tool always fails')

    def run(self) -> None:
        """Serves over stdio until the client closes the connection."""
        self._server.run('stdio')


if __name__ == '__main__':
    TestServer().run()
