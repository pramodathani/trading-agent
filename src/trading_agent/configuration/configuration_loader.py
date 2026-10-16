"""Reads trading_agent.toml into an AgentConfiguration.

Typical usage example:

  loader = ConfigurationLoader(Path('trading_agent.toml'))
  configuration = loader.load()
"""

import tomllib
from pathlib import Path

import pydantic

from trading_agent.configuration import agent_configuration


class ConfigurationError(ValueError):
    """The configuration file is missing, unreadable or invalid."""


class ConfigurationLoader:
    """Reads and checks one configuration file.

    Attributes:
        configuration_path: The TOML file to read.
    """

    def __init__(self, configuration_path: Path):
        """Remembers which file to read, without reading it yet.

        Args:
            configuration_path (Path): The TOML file to read.
        """
        self.configuration_path = configuration_path

    def load(self) -> agent_configuration.AgentConfiguration:
        """Reads the file and checks every value in it.

        Returns:
            agent_configuration.AgentConfiguration: The checked configuration.

        Raises:
            ConfigurationError: The file is missing, is not valid TOML, or holds a value of the wrong kind.
        """
        try:
            text = self.configuration_path.read_text(encoding='utf-8')
        except FileNotFoundError as error:
            raise ConfigurationError(
                f'Configuration file not found: {self.configuration_path}'
            ) from error
        try:
            parsed = tomllib.loads(text)
        except tomllib.TOMLDecodeError as error:
            raise ConfigurationError(
                f'{self.configuration_path} is not valid TOML: {error}'
            ) from error
        try:
            return agent_configuration.AgentConfiguration.model_validate(parsed)
        except pydantic.ValidationError as error:
            raise ConfigurationError(
                f'{self.configuration_path} has invalid values:\n{error}'
            ) from error
