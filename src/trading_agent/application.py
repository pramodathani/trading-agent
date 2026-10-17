"""Builds every component of trading-agent and runs the chosen command.

Typical usage example:

  Application().run()
"""

import asyncio
import logging
import sys
from collections.abc import Sequence

import uvicorn

from trading_agent import command_line
from trading_agent import desk_builder
from trading_agent.client import checkpoint_commands
from trading_agent.client import message_client
from trading_agent.client import proposal_commands
from trading_agent.client import skill_commands
from trading_agent.configuration import agent_configuration
from trading_agent.configuration import configuration_loader
from trading_agent.configuration import secrets as secrets_module
from trading_agent.doctor import doctor
from trading_agent.gateway import access_guard
from trading_agent.gateway import gateway_application
from trading_agent.gateway import token_redacting_filter
from trading_agent.journal import secret_redactor
from trading_agent.journal import trade_journal
from trading_agent.memory import checkpoints as checkpoints_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.skills import skill_usage
from trading_agent.tools import bash_sandbox
from trading_agent.workspace import proposal_store
from trading_agent.workspace import workspace_layout

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

        The process exits with status 2 when the configuration is invalid, and with the command's own status after `doctor`, `send`, `proposals`, `checkpoints` and `skills`.
        """
        arguments = command_line.CommandLine().parse(self._argument_list)
        log_level = logging.INFO
        if arguments.command != 'serve':
            log_level = logging.WARNING
        logging.basicConfig(level=log_level, format=_LOG_FORMAT)
        loader = configuration_loader.ConfigurationLoader(
            arguments.configuration
        )
        try:
            configuration = loader.load()
        except configuration_loader.ConfigurationError as error:
            print(error, file=sys.stderr)
            sys.exit(2)
        secrets = secrets_module.Secrets()
        layout = workspace_layout.WorkspaceLayout(
            configuration.workspace_directory
        )
        desk_names = [desk.name for desk in configuration.desks]
        for created in layout.create_missing(desk_names):
            logging.getLogger(__name__).info(
                'Created %s from its template', created
            )
        if arguments.command == 'doctor':
            sys.exit(doctor.Doctor(configuration, secrets).run())
        if arguments.command == 'send':
            client = message_client.MessageClient(
                f'http://{configuration.gateway.host}:{configuration.gateway.port}',
                secrets.gateway_access_token,
            )
            sys.exit(asyncio.run(client.send(arguments.desk, arguments.text)))
        if arguments.command == 'proposals':
            commands = proposal_commands.ProposalCommands(
                proposal_store.ProposalStore(layout)
            )
            sys.exit(
                commands.run(
                    arguments.proposal_action,
                    vars(arguments).get('proposal_id'),
                )
            )
        if arguments.command == 'checkpoints':
            if arguments.desk not in desk_names:
                print(f'No desk named {arguments.desk!r}', file=sys.stderr)
                sys.exit(1)
            commands = checkpoint_commands.CheckpointCommands(
                checkpoints_module.Checkpoints(
                    layout.checkpoint_repository(arguments.desk),
                    layout.desk_directory(arguments.desk),
                )
            )
            sys.exit(
                commands.run(
                    arguments.checkpoint_action,
                    vars(arguments).get('checkpoint_id'),
                    vars(arguments).get('limit', 20),
                )
            )
        if arguments.command == 'skills':
            sandbox = bash_sandbox.BashSandbox(
                layout.root,
                [],
                configuration.sandbox.passed_environment,
            )
            commands = skill_commands.SkillCommands(
                layout,
                desk_names,
                sandbox.passed_environment(),
            )
            sys.exit(
                commands.run(
                    arguments.skill_action,
                    vars(arguments).get('source'),
                    vars(arguments).get('replace', False),
                )
            )
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
        builder = desk_builder.DeskBuilder(configuration, secrets, event_bus)
        desks = {}
        for desk_configuration in configuration.desks:
            if not desk_configuration.enabled:
                continue
            desks[desk_configuration.name] = builder.build(desk_configuration)
        guard = access_guard.AccessGuard(secrets.gateway_access_token)
        redactor = secret_redactor.SecretRedactor.from_files(
            secrets,
            configuration.tradingmachine_environment_file,
        )
        journal = trade_journal.TradeJournal(
            event_bus,
            workspace_layout.WorkspaceLayout(configuration.workspace_directory),
            redactor,
        )
        usage_tracker = skill_usage.SkillUsageTracker(
            event_bus,
            workspace_layout.WorkspaceLayout(configuration.workspace_directory),
        )
        gateway = gateway_application.GatewayApplication(
            event_bus,
            desks,
            guard,
            [
                journal,
                usage_tracker,
            ],
            redactor,
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
