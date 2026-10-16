"""The shape of trading_agent.toml, checked when it is read.

Each class describes one table of the file. Pydantic checks every value against its type and range, so a typing mistake in the file is reported by name when the program starts.

Typical usage example:

  configuration = AgentConfiguration.model_validate(parsed_toml)
  port = configuration.gateway.port
"""

from pathlib import Path
from typing import Literal

import pydantic


class GatewayConfiguration(pydantic.BaseModel):
    """Where the gateway's web server listens.

    Attributes:
        host: The address to listen on. 127.0.0.1 keeps the gateway reachable from this machine only.
        port: The TCP port to listen on.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    host: str = '127.0.0.1'
    port: int = pydantic.Field(default=8120, gt=0, lt=65536)


class DeskConfiguration(pydantic.BaseModel):
    """One trading desk, which is one independent agent.

    Attributes:
        name: The desk's name, used in folder names, order tags and the web interface.
        enabled: Whether the desk starts with the gateway.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    name: str = pydantic.Field(pattern=r'^[a-z][a-z0-9_]*$')
    enabled: bool = True


class BackendConfiguration(pydantic.BaseModel):
    """One model backend that a desk can use.

    Attributes:
        kind: How the model is reached: "ollama", "openai_compatible" or "claude_code".
        base_url: The server address, needed by the ollama and openai_compatible kinds.
        model: The model name the server knows the model by.
        context_window: How many tokens of context the model is given.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    kind: Literal['ollama', 'openai_compatible', 'claude_code']
    base_url: str | None = None
    model: str
    context_window: int = pydantic.Field(gt=0)

    @pydantic.model_validator(mode='after')
    def _require_base_url_for_servers(self) -> BackendConfiguration:
        """Checks that a backend reached over HTTP has an address.

        Returns:
            BackendConfiguration: This configuration, unchanged.

        Raises:
            ValueError: The kind needs a base_url and none was given.
        """
        if self.kind != 'claude_code' and self.base_url is None:
            raise ValueError(f'base_url is required for kind={self.kind!r}')
        return self


class AgentConfiguration(pydantic.BaseModel):
    """Everything in trading_agent.toml.

    Attributes:
        mode: "dry_run" sends every order to UBI as a dry run, and "live" sends real orders.
        workspace_directory: The folder holding the desks' files, memory and journals.
        tradingmachine_environment_file: The .env file that tradingmachine reads its UBI and MongoDB settings from.
        gateway: Where the web server listens.
        desks: The desks to run.
        backends: The model backends, keyed by the name desks refer to them by.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    mode: Literal['dry_run', 'live'] = 'dry_run'
    workspace_directory: Path = Path('workspace')
    tradingmachine_environment_file: Path
    gateway: GatewayConfiguration = GatewayConfiguration()
    desks: list[DeskConfiguration] = pydantic.Field(min_length=1)
    backends: dict[str, BackendConfiguration] = {}

    @pydantic.model_validator(mode='after')
    def _require_unique_desk_names(self) -> AgentConfiguration:
        """Checks that no two desks share a name.

        Returns:
            AgentConfiguration: This configuration, unchanged.

        Raises:
            ValueError: Two desks have the same name.
        """
        seen_names = set()
        for desk in self.desks:
            if desk.name in seen_names:
                raise ValueError(f'Duplicate desk name: {desk.name!r}')
            seen_names.add(desk.name)
        return self
