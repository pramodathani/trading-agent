"""Tests for MCP servers: the configuration file, real stdio connections, tool_search and call_mcp_tool."""

import asyncio
import contextlib
import json
import sys
from pathlib import Path

import pytest

from trading_agent.extensions import mcp_client_manager
from trading_agent.extensions import mcp_server_configuration
from trading_agent.tools import call_mcp_tool_tool
from trading_agent.tools import tool_search_tool

_TEST_SERVER = Path(__file__).with_name('mcp_test_server.py')


def _write_servers(path: Path, servers: dict) -> Path:
    """Writes an mcp_servers.json file.

    Args:
        path (Path): The file.
        servers (dict): The "mcpServers" object.

    Returns:
        Path: The file.
    """
    path.write_text(
        json.dumps(
            {
                'mcpServers': servers,
            }
        ),
        encoding='utf-8',
    )
    return path


class TestMcpConfiguration:
    """mcp_servers.json is read and expanded."""

    def test_variables_are_expanded_and_types_normalised(
        self,
        tmp_path: Path,
    ) -> None:
        """${NAME}, ${NAME:-default} and "streamable-http" are handled.

        Args:
            tmp_path (Path): A scratch folder.
        """
        path = _write_servers(
            tmp_path / 'mcp_servers.json',
            {
                'news': {
                    'command': 'news-server',
                    'args': [
                        '--token=${NEWS_TOKEN}',
                    ],
                    'env': {
                        'REGION': '${REGION:-in}',
                    },
                },
                'remote': {
                    'type': 'streamable-http',
                    'url': 'https://example.com/mcp',
                    'headers': {
                        'Authorization': 'Bearer ${MISSING_TOKEN}',
                    },
                },
            },
        )
        servers = mcp_server_configuration.McpConfigurationReader(
            path,
            {
                'NEWS_TOKEN': 'abc',
            },
        ).read()
        assert servers[0].args == [
            '--token=abc',
        ]
        assert servers[0].env == {
            'REGION': 'in',
        }
        assert servers[1].type == 'http'
        assert servers[1].headers == {
            'Authorization': 'Bearer ',
        }

    def test_invalid_entries_are_refused(self, tmp_path: Path) -> None:
        """A stdio server without a command and an SSE server are both errors.

        Args:
            tmp_path (Path): A scratch folder.
        """
        for entry in (
            {
                'args': [
                    'x',
                ],
            },
            {
                'type': 'sse',
                'url': 'https://example.com/sse',
            },
        ):
            path = _write_servers(
                tmp_path / 'mcp_servers.json',
                {
                    'bad': entry,
                },
            )
            reader = mcp_server_configuration.McpConfigurationReader(path)
            with pytest.raises(mcp_server_configuration.McpConfigurationError):
                reader.read()

    def test_missing_file_means_no_servers(self, tmp_path: Path) -> None:
        """No file is not an error.

        Args:
            tmp_path (Path): A scratch folder.
        """
        reader = mcp_server_configuration.McpConfigurationReader(
            tmp_path / 'absent.json'
        )
        assert reader.read() == []


class _RunningManager:
    """Runs a manager over the test server for the length of one test."""

    def __init__(self, passed_variable: str):
        """Creates the manager.

        Args:
            passed_variable (str): A variable listed in the server's env.
        """
        configuration = mcp_server_configuration.McpServerConfiguration(
            name='test',
            command=sys.executable,
            args=[
                str(_TEST_SERVER),
            ],
            env={
                passed_variable: 'yes',
            },
        )
        self.manager = mcp_client_manager.McpClientManager(
            [
                configuration,
            ]
        )
        self._task = None

    async def __aenter__(self) -> mcp_client_manager.McpClientManager:
        """Starts the manager and waits for the server to connect.

        Returns:
            mcp_client_manager.McpClientManager: The manager.
        """
        self._task = asyncio.create_task(self.manager.run())
        for _ in range(300):
            if self.manager.settled():
                break
            await asyncio.sleep(0.05)
        return self.manager

    async def __aexit__(self, *exception_details: object) -> None:
        """Stops the manager.

        Args:
            *exception_details (object): The exception, if any, ignored.
        """
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task


class TestMcpConnection:
    """A real stdio server is started, listed and called."""

    def test_tools_are_listed_and_called(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """add answers, fail is reported as an error, and unknown names are refused.

        Args:
            monkeypatch (pytest.MonkeyPatch): Sets a secret for this test only.
        """
        monkeypatch.setenv('GATEWAY_SECRET', 'do-not-leak')

        async def scenario() -> dict:
            """Connects and makes the calls.

            Returns:
                dict: What each call returned.
            """
            async with _RunningManager('PASSED_TO_SERVER') as manager:
                outcomes = {
                    'status': manager.status_lines(),
                    'names': [tool.name for tool in manager.tools()],
                    'add': await manager.call_tool(
                        'test',
                        'add',
                        {
                            'first': 2,
                            'second': 3,
                        },
                        10,
                    ),
                    'fail': await manager.call_tool('test', 'fail', {}, 10),
                    'environment': await manager.call_tool(
                        'test',
                        'environment',
                        {},
                        10,
                    ),
                    'index': manager.index_text(),
                }
                for server, tool_name in (
                    ('test', 'missing'),
                    ('nope', 'add'),
                ):
                    try:
                        await manager.call_tool(server, tool_name, {}, 10)
                    except mcp_client_manager.McpToolError as error:
                        outcomes[f'{server}/{tool_name}'] = str(error)
                return outcomes

        outcomes = asyncio.run(scenario())
        assert outcomes['status'] == [
            'test (stdio): ready, 3 tools',
        ]
        assert outcomes['names'] == [
            'add',
            'environment',
            'fail',
        ]
        assert outcomes['add'].text == '5'
        assert not outcomes['add'].is_error
        assert outcomes['fail'].is_error
        variables = json.loads(outcomes['environment'].text)
        assert 'PASSED_TO_SERVER' in variables
        assert 'GATEWAY_SECRET' not in variables
        assert '- test: add, environment, fail' in outcomes['index']
        assert 'tool_search' in outcomes['test/missing']
        assert 'No MCP server named nope' in outcomes['nope/add']


class _FakeManager:
    """Stands in for the manager with two fixed tools."""

    def tools(self) -> list[mcp_client_manager.McpTool]:
        """Returns two tools on two servers.

        Returns:
            list[mcp_client_manager.McpTool]: The tools.
        """
        return [
            mcp_client_manager.McpTool(
                server='news',
                name='headlines',
                description='Latest market headlines for a stock.',
                input_schema={
                    'type': 'object',
                },
            ),
            mcp_client_manager.McpTool(
                server='maths',
                name='add',
                description='Adds numbers.',
                input_schema={
                    'type': 'object',
                },
            ),
        ]

    async def call_tool(
        self,
        server: str,
        tool_name: str,
        arguments: dict,
        timeout_seconds: float,
    ) -> mcp_client_manager.McpCallResult:
        """Echoes the call.

        Args:
            server (str): The server.
            tool_name (str): The tool.
            arguments (dict): The arguments.
            timeout_seconds (float): Ignored.

        Returns:
            mcp_client_manager.McpCallResult: The call written out.
        """
        del timeout_seconds
        return mcp_client_manager.McpCallResult(
            text=f'{server}/{tool_name} {arguments}',
            is_error=False,
            image_png=None,
        )


class TestMcpTools:
    """tool_search describes tools and call_mcp_tool runs them."""

    def test_search_ranks_by_keywords_and_server_name_lists_all(self) -> None:
        """Keywords find the matching tool; a server name lists its tools; no match lists all names."""
        tool = tool_search_tool.ToolSearchTool(_FakeManager())
        headlines = asyncio.run(
            tool.run(
                tool_search_tool.ToolSearchArguments(query='market headlines')
            )
        )
        assert headlines.text.startswith('server: news\ntool: headlines')
        assert 'maths' not in headlines.text
        by_server = asyncio.run(
            tool.run(tool_search_tool.ToolSearchArguments(query='maths'))
        )
        assert 'tool: add' in by_server.text
        nothing = asyncio.run(
            tool.run(tool_search_tool.ToolSearchArguments(query='weather'))
        )
        assert 'news/headlines, maths/add' in nothing.text

    def test_call_output_is_labelled_as_outside_data(self) -> None:
        """The output says where it came from."""
        tool = call_mcp_tool_tool.CallMcpToolTool(_FakeManager())
        result = asyncio.run(
            tool.run(
                call_mcp_tool_tool.CallMcpToolArguments(
                    server='news',
                    tool='headlines',
                    arguments={
                        'symbol': 'INFY',
                    },
                )
            )
        )
        assert result.text == (
            '[Output of news/headlines, data from outside trading-agent:]\n'
            "news/headlines {'symbol': 'INFY'}"
        )
