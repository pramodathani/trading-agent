"""Checks that mcp_servers.json can be read, and names the servers in it.

It does not start the servers; `trading-agent mcp list` does that.

Typical usage example:

  result = McpServersCheck(Path('mcp_servers.json')).run()
"""

from pathlib import Path

from trading_agent.doctor import doctor_check
from trading_agent.extensions import mcp_server_configuration


class McpServersCheck(doctor_check.DoctorCheck):
    """Checks the MCP server list."""

    name = 'MCP servers (mcp_servers.json)'

    def __init__(self, servers_file: Path):
        """Creates the check.

        Args:
            servers_file (Path): The mcp_servers.json file.
        """
        self._servers_file = servers_file

    def run(self) -> doctor_check.CheckResult:
        """Reads the file.

        Returns:
            doctor_check.CheckResult: OK with the server names, OK with a note when there is no file, or failed when it cannot be read, in which case the gateway will not start.
        """
        try:
            servers = mcp_server_configuration.McpConfigurationReader(
                self._servers_file
            ).read()
        except mcp_server_configuration.McpConfigurationError as error:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.FAILED,
                f'{error}; the gateway will not start until it is fixed.',
            )
        if not servers:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.OK,
                f'No MCP servers configured ({self._servers_file} is absent or empty).',
            )
        names = []
        for server in servers:
            names.append(f'{server.name} ({server.type})')
        return doctor_check.CheckResult(
            doctor_check.CheckStatus.OK,
            f'{len(servers)} configured: {", ".join(names)}. Run `trading-agent mcp list` to connect to them.',
        )
