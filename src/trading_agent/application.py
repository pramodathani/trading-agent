"""Builds every component of trading-agent and runs the chosen command.

Typical usage example:

  Application().run()
"""

import logging
import sys
from collections.abc import Sequence

import uvicorn

from trading_agent import command_line
from trading_agent.configuration import agent_configuration
from trading_agent.configuration import configuration_loader
from trading_agent.configuration import secrets as secrets_module
from trading_agent.doctor import doctor
from trading_agent.gateway import access_guard
from trading_agent.gateway import gateway_application
from trading_agent.gateway import token_redacting_filter
from trading_agent.runtime import desk_runtime
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import no_model_turn_runner

_LOG_FORMAT = '%(asctime)s %(levelname)s %(name)s: %(message)s'


class Application:
    """The whole of trading-agent: its configuration, desks and gateway."""

    def __init__(self, argument_list: Sequence[str] | None = None):
        """Creates the application without reading or starting anything.

        Args:
            argument_list (Sequence[str] | None): The command-line arguments, or None to read them from sys.argv.
        """
        self._argument_list = argument_list

    def run(self) -> None:
        """Reads the configuration and runs the chosen command until it ends.

        The process exits with status 2 when the configuration is invalid, and with the doctor's status after `doctor`.
        """
        logging.basicConfig(level=logging.INFO, format=_LOG_FORMAT)
        arguments = command_line.CommandLine().parse(self._argument_list)
        loader = configuration_loader.ConfigurationLoader(
            arguments.configuration
        )
        try:
            configuration = loader.load()
        except configuration_loader.ConfigurationError as error:
            print(error, file=sys.stderr)
            sys.exit(2)
        secrets = secrets_module.Secrets()
        if arguments.command == 'doctor':
            sys.exit(doctor.Doctor(configuration, secrets).run())
        self._serve(configuration, secrets)

    def _serve(
        self,
        configuration: agent_configuration.AgentConfiguration,
        secrets: secrets_module.Secrets,
    ) -> None:
        """Builds the desks and the gateway and serves until stopped.

        Args:
            configuration (agent_configuration.AgentConfiguration): The agent's configuration.
            secrets (secrets_module.Secrets): The secrets read from the environment and .env.
        """
        event_bus = event_bus_module.EventBus()
        desks = {}
        for desk_configuration in configuration.desks:
            if not desk_configuration.enabled:
                continue
            desks[desk_configuration.name] = desk_runtime.DeskRuntime(
                desk_configuration,
                event_bus,
                no_model_turn_runner.NoModelTurnRunner(),
            )
        guard = access_guard.AccessGuard(secrets.gateway_access_token)
        gateway = gateway_application.GatewayApplication(
            event_bus,
            desks,
            guard,
        )
        server_configuration = uvicorn.Config(
            gateway.build(),
            host=configuration.gateway.host,
            port=configuration.gateway.port,
        )
        token_redacting_filter.TokenRedactingFilter().install()
        try:
            uvicorn.Server(server_configuration).run()
        except KeyboardInterrupt:
            return
