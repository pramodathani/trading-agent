"""Reads mcp_servers.json, which lists the MCP servers every desk can use.

The file uses the "mcpServers" format of Claude Code and Claude Desktop, so a server can be copied from their documentation unchanged:

  {
    "mcpServers": {
      "everything": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-everything"],
        "env": {"SOME_TOKEN": "${SOME_TOKEN}"}
      },
      "deepwiki": {
        "type": "http",
        "url": "https://mcp.deepwiki.com/mcp",
        "headers": {"Authorization": "Bearer ${DEEPWIKI_TOKEN:-}"}
      }
    }
  }

A server started as a program (stdio) receives only a few safe variables, such as PATH and HOME, plus those listed in its "env". `${NAME}` and `${NAME:-default}` in a command, an argument, an env value, a URL or a header are replaced from the gateway's environment, as in Claude Code.

Typical usage example:

  servers = McpConfigurationReader(Path('mcp_servers.json')).read()
"""

import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

import pydantic

_VARIABLE_PATTERN = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}')
_SERVER_NAME_PATTERN = r'^[A-Za-z0-9_-]{1,64}$'


class McpConfigurationError(ValueError):
    """mcp_servers.json is not valid JSON, or a server entry is not valid."""


class McpServerConfiguration(pydantic.BaseModel):
    """One MCP server.

    Attributes:
        name: The server's name, the key in "mcpServers".
        type: "stdio" for a program the gateway starts, "http" for a streamable HTTP server.
        command: The program to start, for stdio.
        args: Its arguments, for stdio.
        env: The environment variables it receives besides the safe defaults, for stdio.
        cwd: The folder to start it in, for stdio, or None for the gateway's folder.
        url: The endpoint, for http.
        headers: HTTP headers sent with every request, for http.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    name: str = pydantic.Field(pattern=_SERVER_NAME_PATTERN)
    type: Literal['stdio', 'http'] = 'stdio'
    command: str | None = None
    args: list[str] = []
    env: dict[str, str] = {}
    cwd: str | None = None
    url: str | None = None
    headers: dict[str, str] = {}

    @pydantic.model_validator(mode='after')
    def _require_what_the_type_needs(self) -> McpServerConfiguration:
        """Checks that a stdio server has a command and an http server a URL.

        Returns:
            McpServerConfiguration: This configuration, unchanged.

        Raises:
            ValueError: The command or URL its type needs is missing.
        """
        if self.type == 'stdio' and not self.command:
            raise ValueError(f'MCP server {self.name!r} needs a "command"')
        if self.type == 'http' and not self.url:
            raise ValueError(f'MCP server {self.name!r} needs a "url"')
        return self


class McpConfigurationReader:
    """Reads and expands mcp_servers.json."""

    def __init__(
        self,
        path: Path,
        environment: Mapping[str, str] | None = None,
    ):
        """Creates the reader.

        Args:
            path (Path): The file.
            environment (Mapping[str, str] | None): Where ${NAME} values come from; None uses os.environ.
        """
        self._path = path
        self._environment = environment

    def read(self) -> list[McpServerConfiguration]:
        """Reads every server, with variables expanded.

        Returns:
            list[McpServerConfiguration]: The servers in file order, or an empty list when the file does not exist.

        Raises:
            McpConfigurationError: The file is not valid JSON, has no "mcpServers" object, or a server is not valid.
        """
        if not self._path.is_file():
            return []
        try:
            data = json.loads(self._path.read_text(encoding='utf-8'))
        except ValueError as error:
            raise McpConfigurationError(
                f'{self._path} is not valid JSON: {error}'
            ) from error
        servers = data.get('mcpServers') if isinstance(data, dict) else None
        if not isinstance(servers, dict):
            raise McpConfigurationError(
                f'{self._path} needs an "mcpServers" object'
            )
        configurations = []
        for name, entry in servers.items():
            configurations.append(self._server(name, entry))
        return configurations

    def _server(self, name: str, entry: object) -> McpServerConfiguration:
        """Checks and expands one server entry.

        Args:
            name (str): The server's name.
            entry (object): Its JSON object.

        Returns:
            McpServerConfiguration: The server.

        Raises:
            McpConfigurationError: The entry is not valid.
        """
        if not isinstance(entry, dict):
            raise McpConfigurationError(f'MCP server {name!r} is not an object')
        fields = dict(entry)
        server_type = fields.get('type', 'stdio')
        if server_type == 'streamable-http':
            server_type = 'http'
        if server_type == 'sse':
            raise McpConfigurationError(
                f'MCP server {name!r} uses the old SSE transport, which is not supported; use its streamable HTTP URL with "type": "http"'
            )
        fields['type'] = server_type
        fields['name'] = name
        for key in ('command', 'cwd', 'url'):
            if isinstance(fields.get(key), str):
                fields[key] = self._expand(fields[key])
        if isinstance(fields.get('args'), list):
            fields['args'] = [
                self._expand(str(item)) for item in fields['args']
            ]
        for key in ('env', 'headers'):
            if isinstance(fields.get(key), dict):
                expanded = {}
                for item_name, value in fields[key].items():
                    expanded[item_name] = self._expand(str(value))
                fields[key] = expanded
        try:
            return McpServerConfiguration.model_validate(fields)
        except pydantic.ValidationError as error:
            raise McpConfigurationError(
                f'MCP server {name!r} is not valid: {error}'
            ) from error

    def _expand(self, text: str) -> str:
        """Replaces ${NAME} and ${NAME:-default} with values from the environment.

        Args:
            text (str): The text.

        Returns:
            str: The text with each variable replaced, by an empty string when it is unset and has no default.
        """
        return _VARIABLE_PATTERN.sub(self._replacement, text)

    def _replacement(self, match: re.Match[str]) -> str:
        """The value for one ${NAME} or ${NAME:-default}.

        Args:
            match (re.Match[str]): The matched variable, with the name in group 1 and the default in group 2.

        Returns:
            str: The variable's value, else the default, else an empty string.
        """
        environment = self._environment
        if environment is None:
            environment = os.environ
        value = environment.get(match.group(1))
        if value:
            return value
        if match.group(2) is not None:
            return match.group(2)
        return ''
