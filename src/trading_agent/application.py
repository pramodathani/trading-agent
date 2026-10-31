"""Builds every component of trading-agent and runs the chosen command.

Typical usage example:

  Application().run()
"""

import asyncio
import datetime
import logging
import sys
import zoneinfo
from collections.abc import Mapping, Sequence
from pathlib import Path

import uvicorn

from trading_agent import command_line
from trading_agent import trader_builder
from trading_agent.channels import notification_formatter
from trading_agent.channels import pairing_store
from trading_agent.channels import telegram_api
from trading_agent.channels import telegram_channel
from trading_agent.channels import telegram_commands
from trading_agent.channels import telegram_requests
from trading_agent.client import app_commands
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
from trading_agent.devices import device_store
from trading_agent.devices import firebase_sender
from trading_agent.devices import push_channel
from trading_agent.doctor import doctor
from trading_agent.extensions import app_catalog
from trading_agent.extensions import hook_runner
from trading_agent.extensions import installed_packages
from trading_agent.extensions import mcp_client_manager
from trading_agent.extensions import mcp_server_configuration
from trading_agent.extensions import systemd_user_units
from trading_agent.gateway import access_guard
from trading_agent.gateway import gateway_application
from trading_agent.gateway import token_redacting_filter
from trading_agent.gateway.routes import account_routes
from trading_agent.gateway.routes import app_routes
from trading_agent.gateway.routes import attachment_routes
from trading_agent.gateway.routes import channel_routes
from trading_agent.gateway.routes import device_routes
from trading_agent.gateway.routes import extension_routes
from trading_agent.gateway.routes import file_routes
from trading_agent.gateway.routes import memory_routes
from trading_agent.gateway.routes import request_routes
from trading_agent.gateway.routes import route_group
from trading_agent.gateway.routes import schedule_routes
from trading_agent.gateway.routes import system_routes
from trading_agent.gateway.routes import trader_routes
from trading_agent.journal import secret_redactor
from trading_agent.journal import trade_journal
from trading_agent.journal import usage_tracker as usage_tracker_module
from trading_agent.memory import checkpoints as checkpoints_module
from trading_agent.requests import request_expiry_watcher
from trading_agent.requests import user_request_responder
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trader_runtime
from trading_agent.scheduling import cron_scheduler
from trading_agent.skills import skill_usage
from trading_agent.subagents import subagent_library
from trading_agent.terminal import gateway_client
from trading_agent.terminal import prompt_history
from trading_agent.terminal import terminal_application
from trading_agent.terminal import terminal_settings
from trading_agent.tools import bash_sandbox
from trading_agent.traders import trader_registry
from trading_agent.traders import trader_store
from trading_agent.workspace import proposal_store
from trading_agent.workspace import trader_migration
from trading_agent.workspace import workspace_layout

_LOG_FORMAT = '%(asctime)s %(levelname)s %(name)s: %(message)s'


class Application:
    """The whole of trading-agent: its configuration, traders and gateway."""

    def __init__(self, argument_list: Sequence[str] | None = None):
        """Creates the application without reading or starting anything.

        Args:
            argument_list (Sequence[str] | None): The command-line arguments, or None to read them from sys.argv.
        """
        self._argument_list = argument_list

    def run(self) -> None:
        """Reads the configuration and runs the chosen command until it ends.

        The process exits with status 2 when the configuration is invalid, and with the command's own status after the terminal program, `doctor`, `send`, `-p`, `proposals`, `checkpoints`, `skills`, `packages`, `subagents` and `mcp`.
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
        trader_migration.TraderMigration(
            layout,
            terminal_settings.TerminalSettings.state_directory()
            / 'terminal.json',
            datetime.datetime.now(zoneinfo.ZoneInfo('Asia/Kolkata')),
        ).run()
        store = trader_store.TraderStore(
            layout,
            configuration.traders,
            tuple(configuration.backends),
        )
        try:
            store.ensure_first()
            trader_names = [record.name for record in store.active()]
        except trader_store.TraderStoreError as error:
            print(error, file=sys.stderr)
            sys.exit(2)
        for created in layout.create_missing(trader_names):
            logging.getLogger(__name__).info(
                'Created %s from its template', created
            )
        if arguments.command == 'doctor':
            sys.exit(doctor.Doctor(configuration, secrets, trader_names).run())
        if arguments.command == 'preflight':
            sys.exit(
                doctor.Doctor(
                    configuration,
                    secrets,
                    trader_names,
                    going_live=True,
                ).run()
            )
        if arguments.command == 'send':
            client = message_client.MessageClient(
                f'http://{configuration.gateway.host}:{configuration.gateway.port}',
                secrets.gateway_access_token,
            )
            sys.exit(asyncio.run(client.send(arguments.trader, arguments.text)))
        if arguments.command == 'print':
            client = message_client.MessageClient(
                f'http://{configuration.gateway.host}:{configuration.gateway.port}',
                secrets.gateway_access_token,
                output_format=arguments.output_format,
            )
            text = arguments.print_text
            if not sys.stdin.isatty():
                piped = sys.stdin.read().strip()
                if piped:
                    text = f'{piped}\n\n{text}'
            sys.exit(
                asyncio.run(
                    client.send(arguments.chosen_trader or 'general', text)
                )
            )
        if arguments.command == 'terminal':
            sys.exit(
                self._terminal(
                    f'http://{configuration.gateway.host}:{configuration.gateway.port}',
                    secrets.gateway_access_token,
                    arguments.chosen_trader,
                )
            )
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
            if arguments.trader not in trader_names:
                print(f'No trader named {arguments.trader!r}', file=sys.stderr)
                sys.exit(1)
            commands = checkpoint_commands.CheckpointCommands(
                checkpoints_module.Checkpoints(
                    layout.checkpoint_repository(arguments.trader),
                    layout.trader_directory(arguments.trader),
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
                trader_names,
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
        if arguments.command == 'apps':
            commands = app_commands.AppCommands(
                app_catalog.AppCatalog(
                    packages,
                    systemd_user_units.SystemdUserUnits(),
                )
            )
            if arguments.app_action == 'enable':
                sys.exit(asyncio.run(commands.enable(arguments.package)))
            if arguments.app_action == 'disable':
                sys.exit(asyncio.run(commands.disable(arguments.package)))
            sys.exit(asyncio.run(commands.list()))
        if arguments.command == 'pairing':
            commands = pairing_commands.PairingCommands(
                pairing_store.PairingStore(layout.telegram_pairing_file),
                configuration.telegram.default_trader,
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

    def _terminal(
        self,
        base_url: str,
        access_token: str,
        trader_name: str | None,
    ) -> int:
        """Runs the terminal program until the user leaves it.

        Args:
            base_url (str): The gateway's address.
            access_token (str): The gateway's access token.
            trader_name (str | None): The trader to open on, or None for the one used last.

        Returns:
            int: 0 when the user left normally, 1 when the gateway refused the token.
        """
        settings = terminal_settings.TerminalSettings.load()
        history = prompt_history.PromptHistory(
            terminal_settings.TerminalSettings.state_directory() / 'history'
        )
        program = terminal_application.TerminalApplication(
            gateway_client.GatewayClient(base_url, access_token),
            settings,
            history,
            trader_name,
        )
        exit_code = program.run()
        if program.problem is not None:
            print(program.problem, file=sys.stderr)
        return exit_code or 0

    def _serve(
        self,
        configuration: agent_configuration.AgentConfiguration,
        secrets: secrets_module.Secrets,
        manager: mcp_client_manager.McpClientManager,
        packages: installed_packages.InstalledPackages,
    ) -> None:
        """Builds the traders and the gateway and serves until stopped.

        Args:
            configuration (agent_configuration.AgentConfiguration): The agent's configuration.
            secrets (secrets_module.Secrets): The secrets read from the environment and .env.
            manager (mcp_client_manager.McpClientManager): The MCP connections, run beside the traders.
            packages (installed_packages.InstalledPackages): The installed packages, whose hooks run beside the user's.
        """
        event_bus = event_bus_module.EventBus()
        layout = workspace_layout.WorkspaceLayout(
            configuration.workspace_directory
        )
        store = trader_store.TraderStore(
            layout,
            configuration.traders,
            tuple(configuration.backends),
        )
        active_names = [record.name for record in store.active()]
        model_usage = usage_tracker_module.UsageTracker(
            event_bus,
            layout,
            active_names,
            configuration.backends,
        )
        builder = trader_builder.TraderBuilder(
            configuration,
            secrets,
            event_bus,
            manager,
            model_usage,
        )
        registry = trader_registry.TraderRegistry(
            store, builder, layout, event_bus
        )
        registry.load()
        traders = registry.traders
        guard = access_guard.AccessGuard(secrets.gateway_access_token)
        responder = user_request_responder.UserRequestResponder(
            builder.user_request_store,
            event_bus,
            traders,
            registry.tool_registries,
            builder.permission_grants,
        )
        redactor = secret_redactor.SecretRedactor.from_files(
            secrets,
            configuration.tradingmachine_environment_file,
        )
        journal = trade_journal.TradeJournal(
            event_bus,
            layout,
            redactor,
        )
        scheduler = cron_scheduler.CronScheduler(
            registry.schedules,
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
            layout,
        )
        pairing = pairing_store.PairingStore(layout.telegram_pairing_file)
        telegram = self._telegram_channel(
            configuration,
            secrets,
            builder,
            traders,
            event_bus,
            pairing,
            responder,
        )
        workers = [
            journal,
            skill_uses,
            model_usage,
            manager,
            hooks,
            scheduler,
            builder.market_watcher(traders),
            request_expiry_watcher.RequestExpiryWatcher(
                builder.user_request_store,
                responder,
            ),
        ]
        if telegram is not None:
            workers.append(telegram)
        phones = device_store.DeviceStore(layout.phone_devices_file)
        push, push_problem = self._push_channel(
            configuration, secrets, event_bus, phones
        )
        if push is not None:
            workers.append(push)
        route_groups = self._route_groups(
            configuration,
            builder,
            traders,
            guard,
            scheduler,
            model_usage,
            manager,
            redactor,
            pairing,
            bool(secrets.telegram_bot_token),
            telegram,
            responder,
        )
        route_groups.append(
            device_routes.DeviceRoutes(guard, phones, push, push_problem)
        )
        gateway = gateway_application.GatewayApplication(
            event_bus,
            traders,
            guard,
            workers,
            redactor,
            secrets.webhook_token,
            route_groups,
            configuration.gateway.frontend_directory,
            configuration.gateway.allowed_origins,
            registry,
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
        builder: trader_builder.TraderBuilder,
        traders: Mapping[str, trader_runtime.TraderRuntime],
        guard: access_guard.AccessGuard,
        scheduler: cron_scheduler.CronScheduler,
        model_usage: usage_tracker_module.UsageTracker,
        manager: mcp_client_manager.McpClientManager,
        redactor: secret_redactor.SecretRedactor,
        pairing: pairing_store.PairingStore,
        telegram_token_present: bool,
        telegram: telegram_channel.TelegramChannel | None,
        responder: user_request_responder.UserRequestResponder,
    ) -> list[route_group.RouteGroup]:
        """Creates every route group of the gateway's API.

        Args:
            configuration (agent_configuration.AgentConfiguration): The agent's configuration.
            builder (trader_builder.TraderBuilder): The builder that made the traders, holding their parts.
            traders (Mapping[str, trader_runtime.TraderRuntime]): The running traders.
            guard (access_guard.AccessGuard): Checks the access token.
            scheduler (cron_scheduler.CronScheduler): The cron scheduler.
            model_usage (usage_tracker_module.UsageTracker): Today's model usage.
            manager (mcp_client_manager.McpClientManager): The MCP connections.
            redactor (secret_redactor.SecretRedactor): Masks secrets.
            pairing (pairing_store.PairingStore): The Telegram pairing file.
            telegram_token_present (bool): Whether a Telegram bot token is set.
            telegram (telegram_channel.TelegramChannel | None): The running Telegram channel, or None.
            responder (user_request_responder.UserRequestResponder): Records the user's responses to the traders' requests.

        Returns:
            list[route_group.RouteGroup]: The route groups.
        """
        parts = builder.trader_parts()
        shared = builder.shared_parts()
        return [
            trader_routes.TraderRoutes(
                traders,
                guard,
                parts,
                shared.layout,
                configuration.mode,
                shared.attachments,
                configuration.backends,
            ),
            attachment_routes.AttachmentRoutes(
                traders,
                shared.attachments,
                shared.layout,
                guard,
            ),
            account_routes.AccountRoutes(guard, shared, traders),
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
                traders,
            ),
            channel_routes.ChannelRoutes(
                guard,
                pairing,
                configuration.telegram,
                telegram_token_present,
                telegram,
            ),
            app_routes.AppRoutes(
                guard,
                app_catalog.AppCatalog(
                    shared.packages,
                    systemd_user_units.SystemdUserUnits(),
                ),
            ),
            request_routes.RequestRoutes(
                guard,
                builder.user_request_store,
                responder,
                builder.permission_grants,
            ),
        ]

    def _push_channel(
        self,
        configuration: agent_configuration.AgentConfiguration,
        secrets: secrets_module.Secrets,
        event_bus: event_bus_module.EventBus,
        phones: device_store.DeviceStore,
    ) -> tuple[push_channel.PushChannel | None, str]:
        """Builds the push channel for the Android app, when it is switched on and has a Firebase key.

        Args:
            configuration (agent_configuration.AgentConfiguration): The agent's configuration.
            secrets (secrets_module.Secrets): The secrets, holding the Firebase key file's path.
            event_bus (event_bus_module.EventBus): The event bus.
            phones (device_store.DeviceStore): The registered phones.

        Returns:
            tuple[push_channel.PushChannel | None, str]: The channel, or None with the reason push is off.
        """
        settings = configuration.push
        if not settings.enabled:
            return (
                None,
                'Push notifications are off: [push] enabled is false in trading_agent.toml.',
            )
        if not secrets.firebase_service_account_file:
            problem = 'Push notifications are off: TRADING_AGENT_FIREBASE_SERVICE_ACCOUNT_FILE is not set in .env.'
            logging.getLogger(__name__).warning(problem)
            return None, problem
        try:
            sender = firebase_sender.FirebaseSender(
                Path(secrets.firebase_service_account_file).expanduser()
            )
        except (OSError, ValueError) as error:
            problem = f'Push notifications are off: the Firebase key file could not be read ({error}).'
            logging.getLogger(__name__).warning(problem)
            return None, problem
        channel = push_channel.PushChannel(
            phones,
            sender,
            notification_formatter.NotificationFormatter(
                settings.notifications
            ),
            event_bus,
            settings.notifications,
        )
        return channel, ''

    def _telegram_channel(
        self,
        configuration: agent_configuration.AgentConfiguration,
        secrets: secrets_module.Secrets,
        builder: trader_builder.TraderBuilder,
        traders: Mapping[str, trader_runtime.TraderRuntime],
        event_bus: event_bus_module.EventBus,
        pairing: pairing_store.PairingStore,
        responder: user_request_responder.UserRequestResponder,
    ) -> telegram_channel.TelegramChannel | None:
        """Builds the Telegram channel, when it is switched on and has a token.

        Args:
            configuration (agent_configuration.AgentConfiguration): The agent's configuration.
            secrets (secrets_module.Secrets): The secrets, holding the bot token.
            builder (trader_builder.TraderBuilder): The builder, for the shared and trader parts.
            traders (Mapping[str, trader_runtime.TraderRuntime]): The running traders.
            event_bus (event_bus_module.EventBus): The event bus.
            pairing (pairing_store.PairingStore): The pairing file.
            responder (user_request_responder.UserRequestResponder): Records answers given with Telegram's buttons.

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
        api = telegram_api.TelegramApi(
            secrets.telegram_bot_token, settings.poll_seconds
        )
        return telegram_channel.TelegramChannel(
            api,
            pairing,
            telegram_commands.TelegramCommands(
                traders,
                builder.shared_parts(),
                pairing,
                configuration.mode,
                request_store=builder.user_request_store,
                responder=responder,
            ),
            notification_formatter.NotificationFormatter(
                settings.notifications
            ),
            traders,
            builder.trader_parts(),
            event_bus,
            settings.default_trader,
            builder.shared_parts().attachments,
            telegram_requests.TelegramRequests(
                api,
                pairing,
                builder.user_request_store,
                responder,
            ),
        )
