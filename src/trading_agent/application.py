"""Builds every component of trading-agent and runs the chosen command.

Typical usage example:

  Application().run()
"""

import asyncio
import logging
import sys
from collections.abc import Mapping, Sequence

import uvicorn

from trading_agent import command_line
from trading_agent import desk_builder
from trading_agent.channels import notification_formatter
from trading_agent.channels import pairing_store
from trading_agent.channels import telegram_api
from trading_agent.channels import telegram_channel
from trading_agent.channels import telegram_commands
from trading_agent.client import checkpoint_commands
from trading_agent.client import mcp_commands
from trading_agent.client import message_client
from trading_agent.client import package_commands
from trading_agent.client import pairing_commands
from trading_agent.client import proposal_commands
from trading_agent.client import skill_commands
from trading_agent.client import subagent_commands
from trading_agent.configuration import agent_configuration
from trading_agent.configuration import configuration_loader
from trading_agent.configuration import secrets as secrets_module
from trading_agent.doctor import doctor
from trading_agent.extensions import hook_runner
from trading_agent.extensions import installed_packages
from trading_agent.extensions import mcp_client_manager
from trading_agent.extensions import mcp_server_configuration
from trading_agent.gateway import access_guard
from trading_agent.gateway import gateway_application
from trading_agent.gateway import token_redacting_filter
from trading_agent.gateway.routes import account_routes
from trading_agent.gateway.routes import channel_routes
from trading_agent.gateway.routes import desk_routes
from trading_agent.gateway.routes import extension_routes
from trading_agent.gateway.routes import file_routes
from trading_agent.gateway.routes import memory_routes
from trading_agent.gateway.routes import route_group
from trading_agent.gateway.routes import schedule_routes
from trading_agent.gateway.routes import system_routes
from trading_agent.journal import secret_redactor
from trading_agent.journal import trade_journal
from trading_agent.journal import usage_tracker as usage_tracker_module
from trading_agent.memory import checkpoints as checkpoints_module
from trading_agent.runtime import desk_runtime
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.scheduling import cron_scheduler
from trading_agent.skills import skill_usage
from trading_agent.subagents import subagent_library
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

        The process exits with status 2 when the configuration is invalid, and with the command's own status after `doctor`, `send`, `proposals`, `checkpoints`, `skills`, `packages`, `subagents` and `mcp`.
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
        packages = installed_packages.InstalledPackages(
            layout.packages_directory
        )
        if arguments.command == 'packages':
            commands = package_commands.PackageCommands(packages)
            argument = vars(arguments).get('source') or vars(arguments).get(
                'name'
            )
            sys.exit(
                commands.run(
                    arguments.package_action,
                    argument,
                    vars(arguments).get('replace', False),
                )
            )
        if arguments.command == 'pairing':
            commands = pairing_commands.PairingCommands(
                pairing_store.PairingStore(layout.telegram_pairing_file),
                configuration.telegram.default_desk,
            )
            if arguments.pairing_action == 'approve':
                sys.exit(commands.approve(arguments.code))
            if arguments.pairing_action == 'revoke':
                sys.exit(commands.revoke(arguments.chat_id))
            sys.exit(commands.list())
        if arguments.command == 'subagents':
            library = subagent_library.SubagentLibrary(
                layout.agents_directory,
                packages.agent_roots,
            )
            sys.exit(subagent_commands.SubagentCommands(library).list())
        try:
            mcp_servers = mcp_server_configuration.McpConfigurationReader(
                configuration.mcp_servers_file
            ).read_with_packages(packages.mcp_files())
        except mcp_server_configuration.McpConfigurationError as error:
            print(error, file=sys.stderr)
            sys.exit(2)
        manager = mcp_client_manager.McpClientManager(mcp_servers)
        if arguments.command == 'mcp':
            sys.exit(asyncio.run(mcp_commands.McpCommands(manager).list()))
        self._serve(configuration, secrets, manager, packages)

    def _serve(
        self,
        configuration: agent_configuration.AgentConfiguration,
        secrets: secrets_module.Secrets,
        manager: mcp_client_manager.McpClientManager,
        packages: installed_packages.InstalledPackages,
    ) -> None:
        """Builds the desks and the gateway and serves until stopped.

        Args:
            configuration (agent_configuration.AgentConfiguration): The agent's configuration.
            secrets (secrets_module.Secrets): The secrets read from the environment and .env.
            manager (mcp_client_manager.McpClientManager): The MCP connections, run beside the desks.
            packages (installed_packages.InstalledPackages): The installed packages, whose hooks run beside the user's.
        """
        event_bus = event_bus_module.EventBus()
        enabled_desk_names = []
        for desk_configuration in configuration.desks:
            if desk_configuration.enabled:
                enabled_desk_names.append(desk_configuration.name)
        model_usage = usage_tracker_module.UsageTracker(
            event_bus,
            workspace_layout.WorkspaceLayout(configuration.workspace_directory),
            enabled_desk_names,
            configuration.backends,
        )
        builder = desk_builder.DeskBuilder(
            configuration,
            secrets,
            event_bus,
            manager,
            model_usage,
        )
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
        layout = workspace_layout.WorkspaceLayout(
            configuration.workspace_directory
        )
        schedules = {}
        for name, desk in desks.items():
            schedules[name] = builder.desk_schedule(desk)
        scheduler = cron_scheduler.CronScheduler(
            schedules,
            builder.calendar,
            builder.hours,
            event_bus,
            redactor,
        )
        hooks = hook_runner.HookRunner(
            event_bus,
            layout.hooks_directory,
            packages,
            redactor,
        )
        skill_uses = skill_usage.SkillUsageTracker(
            event_bus,
            workspace_layout.WorkspaceLayout(configuration.workspace_directory),
        )
        pairing = pairing_store.PairingStore(layout.telegram_pairing_file)
        telegram = self._telegram_channel(
            configuration,
            secrets,
            builder,
            desks,
            event_bus,
            pairing,
        )
        workers = [
            journal,
            skill_uses,
            model_usage,
            manager,
            hooks,
            scheduler,
            builder.market_watcher(desks),
        ]
        if telegram is not None:
            workers.append(telegram)
        gateway = gateway_application.GatewayApplication(
            event_bus,
            desks,
            guard,
            workers,
            redactor,
            secrets.webhook_token,
            self._route_groups(
                configuration,
                builder,
                desks,
                guard,
                scheduler,
                model_usage,
                manager,
                redactor,
                pairing,
                bool(secrets.telegram_bot_token),
                telegram,
            ),
            configuration.gateway.frontend_directory,
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

    def _route_groups(
        self,
        configuration: agent_configuration.AgentConfiguration,
        builder: desk_builder.DeskBuilder,
        desks: Mapping[str, desk_runtime.DeskRuntime],
        guard: access_guard.AccessGuard,
        scheduler: cron_scheduler.CronScheduler,
        model_usage: usage_tracker_module.UsageTracker,
        manager: mcp_client_manager.McpClientManager,
        redactor: secret_redactor.SecretRedactor,
        pairing: pairing_store.PairingStore,
        telegram_token_present: bool,
        telegram: telegram_channel.TelegramChannel | None,
    ) -> list[route_group.RouteGroup]:
        """Creates every route group of the gateway's API.

        Args:
            configuration (agent_configuration.AgentConfiguration): The agent's configuration.
            builder (desk_builder.DeskBuilder): The builder that made the desks, holding their parts.
            desks (Mapping[str, desk_runtime.DeskRuntime]): The running desks.
            guard (access_guard.AccessGuard): Checks the access token.
            scheduler (cron_scheduler.CronScheduler): The cron scheduler.
            model_usage (usage_tracker_module.UsageTracker): Today's model usage.
            manager (mcp_client_manager.McpClientManager): The MCP connections.
            redactor (secret_redactor.SecretRedactor): Masks secrets.
            pairing (pairing_store.PairingStore): The Telegram pairing file.
            telegram_token_present (bool): Whether a Telegram bot token is set.
            telegram (telegram_channel.TelegramChannel | None): The running Telegram channel, or None.

        Returns:
            list[route_group.RouteGroup]: The route groups.
        """
        parts = builder.desk_parts()
        shared = builder.shared_parts()
        desk_names = list(desks)
        return [
            desk_routes.DeskRoutes(
                desks,
                guard,
                parts,
                shared.layout,
                configuration.mode,
            ),
            account_routes.AccountRoutes(guard, shared, desk_names),
            memory_routes.MemoryRoutes(guard, parts, shared.layout),
            file_routes.FileRoutes(
                guard,
                shared.layout,
                parts,
                shared.proposals,
            ),
            schedule_routes.ScheduleRoutes(guard, parts, scheduler),
            extension_routes.ExtensionRoutes(guard, parts, shared, manager),
            system_routes.SystemRoutes(
                guard,
                configuration,
                model_usage,
                redactor,
                desk_names,
            ),
            channel_routes.ChannelRoutes(
                guard,
                pairing,
                configuration.telegram,
                telegram_token_present,
                telegram,
            ),
        ]

    def _telegram_channel(
        self,
        configuration: agent_configuration.AgentConfiguration,
        secrets: secrets_module.Secrets,
        builder: desk_builder.DeskBuilder,
        desks: Mapping[str, desk_runtime.DeskRuntime],
        event_bus: event_bus_module.EventBus,
        pairing: pairing_store.PairingStore,
    ) -> telegram_channel.TelegramChannel | None:
        """Builds the Telegram channel, when it is switched on and has a token.

        Args:
            configuration (agent_configuration.AgentConfiguration): The agent's configuration.
            secrets (secrets_module.Secrets): The secrets, holding the bot token.
            builder (desk_builder.DeskBuilder): The builder, for the shared and desk parts.
            desks (Mapping[str, desk_runtime.DeskRuntime]): The running desks.
            event_bus (event_bus_module.EventBus): The event bus.
            pairing (pairing_store.PairingStore): The pairing file.

        Returns:
            telegram_channel.TelegramChannel | None: The channel, or None when Telegram is off or has no token.
        """
        settings = configuration.telegram
        if not settings.enabled:
            return None
        if not secrets.telegram_bot_token:
            logging.getLogger(__name__).warning(
                '[telegram] is enabled but TRADING_AGENT_TELEGRAM_BOT_TOKEN is not set; Telegram stays off'
            )
            return None
        return telegram_channel.TelegramChannel(
            telegram_api.TelegramApi(
                secrets.telegram_bot_token, settings.poll_seconds
            ),
            pairing,
            telegram_commands.TelegramCommands(
                desks,
                builder.shared_parts(),
                pairing,
                configuration.mode,
            ),
            notification_formatter.NotificationFormatter(
                settings.notifications
            ),
            desks,
            builder.desk_parts(),
            event_bus,
            settings.default_desk,
        )
