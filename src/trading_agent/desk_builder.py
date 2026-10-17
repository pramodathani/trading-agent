"""Builds one desk with its tools, model backend and turn runner.

Each milestone adds parts to a desk, so this one class is where they are put together. Every backend in the desk's backend_order becomes a route of the desk's model router, most preferred first.

Typical usage example:

  desk = DeskBuilder(configuration, secrets, event_bus).build(desk_configuration)
"""

import datetime
import functools
import logging
import os
from collections.abc import Mapping
from pathlib import Path

from trading_agent.agent import agent_loop
from trading_agent.agent import agent_turn_runner
from trading_agent.agent import context_compressor
from trading_agent.agent import loop_guard
from trading_agent.agent import prompt_builder
from trading_agent.backends import backend as backend_module
from trading_agent.backends import claude_code_turn_runner
from trading_agent.backends import claude_tool_bridge
from trading_agent.backends import model_router
from trading_agent.backends import ollama_backend
from trading_agent.backends import openai_compatible_backend
from trading_agent.configuration import agent_configuration
from trading_agent.configuration import secrets as secrets_module
from trading_agent.extensions import installed_packages
from trading_agent.extensions import mcp_client_manager
from trading_agent.gateway import gateway_parts
from trading_agent.journal import usage_tracker as usage_tracker_module
from trading_agent.knowledge import knowledge_base
from trading_agent.memory import checkpoints as checkpoints_module
from trading_agent.memory import session_keeper
from trading_agent.memory import session_search
from trading_agent.memory import session_store
from trading_agent.risk import account_snapshot
from trading_agent.risk import exchange_hours
from trading_agent.risk import kill_switch
from trading_agent.risk import margin_estimator
from trading_agent.risk import risk_engine
from trading_agent.risk import risk_ledger
from trading_agent.risk import trading_limits
from trading_agent.runtime import desk_runtime
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import no_model_turn_runner
from trading_agent.runtime import steering_inbox as steering_inbox_module
from trading_agent.runtime import turn_runner
from trading_agent.scheduling import built_in_jobs
from trading_agent.scheduling import command_job_runner
from trading_agent.scheduling import cron_job
from trading_agent.scheduling import cron_job_store
from trading_agent.scheduling import cron_scheduler
from trading_agent.scheduling import market_calendar
from trading_agent.scheduling import market_status
from trading_agent.scheduling import market_watcher
from trading_agent.scheduling import price_alert_store
from trading_agent.skills import skill_curator
from trading_agent.skills import skill_library
from trading_agent.skills import skill_usage
from trading_agent.skills import skill_writer
from trading_agent.subagents import subagent_library
from trading_agent.subagents import subagent_runner
from trading_agent.subagents import subagent_toolbox
from trading_agent.tools import add_note_tool
from trading_agent.tools import address_guard
from trading_agent.tools import bash_background_tool
from trading_agent.tools import bash_check_tool
from trading_agent.tools import bash_restart_tool
from trading_agent.tools import bash_run_tool
from trading_agent.tools import bash_sandbox
from trading_agent.tools import bash_session
from trading_agent.tools import browser_back_tool
from trading_agent.tools import browser_click_tool
from trading_agent.tools import browser_open_tool
from trading_agent.tools import browser_screenshot_tool
from trading_agent.tools import browser_session
from trading_agent.tools import browser_snapshot_tool
from trading_agent.tools import browser_tabs_tool
from trading_agent.tools import browser_type_tool
from trading_agent.tools import call_mcp_tool_tool
from trading_agent.tools import cancel_order_tool
from trading_agent.tools import cancel_price_alert_tool
from trading_agent.tools import cron_create_tool
from trading_agent.tools import cron_delete_tool
from trading_agent.tools import cron_list_tool
from trading_agent.tools import delegate_task_tool
from trading_agent.tools import edit_file_tool
from trading_agent.tools import flatten_desk_tool
from trading_agent.tools import get_candles_tool
from trading_agent.tools import get_orders_tool
from trading_agent.tools import get_portfolio_tool
from trading_agent.tools import get_quote_tool
from trading_agent.tools import get_time_tool
from trading_agent.tools import load_skill_tool
from trading_agent.tools import modify_order_tool
from trading_agent.tools import order_tool
from trading_agent.tools import path_policy
from trading_agent.tools import place_bracket_order_tool
from trading_agent.tools import place_order_tool
from trading_agent.tools import propose_file_change_tool
from trading_agent.tools import read_file_tool
from trading_agent.tools import schedule_wakeup_tool
from trading_agent.tools import search_instruments_tool
from trading_agent.tools import search_knowledge_tool
from trading_agent.tools import search_sessions_tool
from trading_agent.tools import send_message_tool
from trading_agent.tools import set_price_alert_tool
from trading_agent.tools import skill_archive_tool
from trading_agent.tools import skill_create_tool
from trading_agent.tools import skill_patch_tool
from trading_agent.tools import tool_call_executor
from trading_agent.tools import tool_registry
from trading_agent.tools import tool_search_tool
from trading_agent.tools import web_fetch_tool
from trading_agent.tools import web_search_tool
from trading_agent.tools import write_file_tool
from trading_agent.trading import broker_reader
from trading_agent.trading import desk_order_book
from trading_agent.trading import result_formatter
from trading_agent.workspace import proposal_store
from trading_agent.workspace import workspace_layout

_LOGGER = logging.getLogger(__name__)


class DeskBuilder:
    """Puts a desk together from the configuration."""

    def __init__(
        self,
        configuration: agent_configuration.AgentConfiguration,
        secrets: secrets_module.Secrets,
        event_bus: event_bus_module.EventBus,
        mcp_manager: mcp_client_manager.McpClientManager | None = None,
        usage_tracker: usage_tracker_module.UsageTracker | None = None,
    ):
        """Creates the builder.

        Args:
            configuration (agent_configuration.AgentConfiguration): The agent's configuration.
            secrets (secrets_module.Secrets): The secrets read from the environment and .env.
            event_bus (event_bus_module.EventBus): The bus every desk publishes on.
            mcp_manager (mcp_client_manager.McpClientManager | None): The gateway's MCP connections, shared by every desk, or None.
            usage_tracker (usage_tracker_module.UsageTracker | None): Today's model usage, for /usage, or None.
        """
        self._configuration = configuration
        self._secrets = secrets
        self._event_bus = event_bus
        self._mcp_manager = mcp_manager
        self._usage_tracker = usage_tracker
        self._alert_stores: dict[str, price_alert_store.PriceAlertStore] = {}
        self._desk_parts: dict[str, gateway_parts.DeskParts] = {}
        self._steering_inboxes: dict[
            str, steering_inbox_module.SteeringInbox
        ] = {}
        self._layout = workspace_layout.WorkspaceLayout(
            configuration.workspace_directory
        )
        self._proposal_store = proposal_store.ProposalStore(self._layout)
        self._broker_reader = broker_reader.BrokerReader(
            configuration.tradingmachine_environment_file
        )
        self._result_formatter = result_formatter.ResultFormatter()
        self.calendar = market_calendar.MarketCalendar(
            configuration.market_calendar_directory
        )
        self.hours = exchange_hours.ExchangeHours(self.calendar)
        self._schedule_parts: dict[str, tuple] = {}
        self._order_services = self._build_order_services()
        self._skill_libraries: dict[str, skill_library.SkillLibrary] = {}
        self._packages = installed_packages.InstalledPackages(
            self._layout.packages_directory
        )
        self._subagent_library = subagent_library.SubagentLibrary(
            self._layout.agents_directory,
            self._packages.agent_roots,
        )
        self._knowledge_base = knowledge_base.KnowledgeBase(
            self._layout.knowledge_directory,
            self._layout.knowledge_index_file,
        )

    def _build_order_services(self) -> order_tool.OrderServices:
        """Builds the one risk engine and order book that every desk shares.

        Returns:
            order_tool.OrderServices: What the order tools use.
        """
        ledger = risk_ledger.RiskLedger(self._layout.risk_ledger_file)
        snapshot_reader = account_snapshot.AccountSnapshotReader(
            self._broker_reader
        )
        risk_settings = self._configuration.risk
        self._kill_switch = kill_switch.KillSwitch(
            self._broker_reader,
            ledger,
            self._event_bus,
            self._configuration.mode,
        )
        services = risk_engine.RiskServices(
            limits_reader=trading_limits.TradingLimitsReader(
                self._layout.trading_rules_file
            ),
            snapshot_reader=snapshot_reader,
            ledger=ledger,
            kill_switch=self._kill_switch,
            margin_estimator=margin_estimator.MarginEstimator(
                risk_settings.margin_rates
            ),
            exchange_hours=self.hours,
        )
        engine = risk_engine.RiskEngine(
            services,
            self._event_bus,
            datetime.timedelta(minutes=risk_settings.ownership_grace_minutes),
        )
        return order_tool.OrderServices(
            reader=self._broker_reader,
            risk_engine=engine,
            order_book=desk_order_book.DeskOrderBook(
                self._layout.desk_orders_file
            ),
            snapshot_reader=snapshot_reader,
            ledger=ledger,
            event_bus=self._event_bus,
            formatter=self._result_formatter,
        )

    def build(
        self,
        desk_configuration: agent_configuration.DeskConfiguration,
    ) -> desk_runtime.DeskRuntime:
        """Builds one desk.

        Args:
            desk_configuration (agent_configuration.DeskConfiguration): The desk's settings.

        Returns:
            desk_runtime.DeskRuntime: The desk, not yet running.
        """
        desk_name = desk_configuration.name
        self._steering_inboxes[desk_name] = steering_inbox_module.SteeringInbox(
            self._event_bus,
            desk_name,
        )
        checkpoints = checkpoints_module.Checkpoints(
            self._layout.checkpoint_repository(desk_name),
            self._layout.desk_directory(desk_name),
        )
        store = session_store.SessionStore(
            self._layout.sessions_directory(desk_name)
        )
        sandbox = bash_sandbox.BashSandbox(
            self._layout.scratch_directory(desk_name),
            self._configuration.sandbox.hidden_paths,
            self._configuration.sandbox.passed_environment,
        )
        library = skill_library.SkillLibrary(
            self._layout.installed_skills_directory,
            self._layout.agent_skills_directory(desk_name),
            environment=sandbox.passed_environment(),
            package_skill_roots=self._packages.skill_roots,
        )
        self._skill_libraries[desk_name] = library
        writer = skill_writer.SkillWriter(
            library,
            checkpoints,
            self._layout.skill_ledger_file(desk_name),
        )
        jobs = cron_job_store.CronJobStore(
            self._layout.cron_directory(desk_name)
        )
        built_ins = built_in_jobs.BuiltInJobs().jobs(
            desk_configuration.heartbeat_minutes,
            desk_configuration.rollover_time,
            desk_configuration.scheduled_checks,
        )
        alerts = price_alert_store.PriceAlertStore(
            self._layout.alerts_file(desk_name)
        )
        self._alert_stores[desk_name] = alerts
        executor = self._executor(
            desk_configuration,
            checkpoints,
            sandbox,
            library,
            writer,
            jobs,
            built_ins,
            alerts,
        )
        self._desk_parts[desk_name] = gateway_parts.DeskParts(
            sessions=store,
            jobs=jobs,
            built_in_jobs=built_ins,
            alerts=alerts,
            skills=library,
            checkpoints=checkpoints,
            tools=executor.tool_registry,
        )
        runner = self._turn_runner(desk_configuration, executor, store)
        keeper = None
        if isinstance(runner, model_router.ModelRouter):
            curator = skill_curator.SkillCurator(
                library,
                skill_usage.SkillUsageReader(
                    self._layout.skill_usage_file(desk_name)
                ),
                writer,
                self._configuration.skills.archive_after_days,
            )
            keeper = session_keeper.SessionKeeper(
                desk_name,
                runner,
                store,
                self._event_bus,
                curator,
            )
        return desk_runtime.DeskRuntime(
            desk_configuration,
            self._event_bus,
            runner,
            self._configuration.mode,
            executor.tool_registry,
            keeper,
            library,
            self._usage_tracker,
            market_status.MarketStatus(self.calendar, self.hours),
            self._steering_inboxes[desk_name],
        )

    def desk_parts(self) -> dict[str, gateway_parts.DeskParts]:
        """The stores and tools of every desk build() made, for the gateway's API.

        Returns:
            dict[str, gateway_parts.DeskParts]: The parts, keyed by desk name.
        """
        return dict(self._desk_parts)

    def shared_parts(self) -> gateway_parts.SharedParts:
        """The parts every desk shares, for the gateway's API.

        Returns:
            gateway_parts.SharedParts: The shared parts.
        """
        return gateway_parts.SharedParts(
            layout=self._layout,
            reader=self._broker_reader,
            snapshot_reader=self._order_services.snapshot_reader,
            risk_engine=self._order_services.risk_engine,
            ledger=self._order_services.ledger,
            kill_switch=self._kill_switch,
            order_book=self._order_services.order_book,
            proposals=self._proposal_store,
            subagents=self._subagent_library,
            packages=self._packages,
            calendar=self.calendar,
        )

    def market_watcher(
        self,
        desks: Mapping[str, desk_runtime.DeskRuntime],
    ) -> market_watcher.MarketWatcher:
        """The market watcher over the desks build() made.

        Args:
            desks (Mapping[str, desk_runtime.DeskRuntime]): The desks, keyed by name.

        Returns:
            market_watcher.MarketWatcher: The watcher, sharing the desks' order book, risk engine and alert stores.
        """
        return market_watcher.MarketWatcher(
            desks,
            self._alert_stores,
            self._order_services.order_book,
            self._broker_reader,
            self._order_services.risk_engine,
            self.hours,
            self._event_bus,
            self._layout.market_watcher_state_file,
        )

    def desk_schedule(
        self,
        desk: desk_runtime.DeskRuntime,
    ) -> cron_scheduler.DeskSchedule:
        """What the cron scheduler needs for a desk that build() made.

        Args:
            desk (desk_runtime.DeskRuntime): The desk.

        Returns:
            cron_scheduler.DeskSchedule: Its jobs, built-in jobs, command runner and subagent runner.
        """
        jobs, built_ins, sandbox, subagents = self._schedule_parts[desk.name]
        return cron_scheduler.DeskSchedule(
            desk=desk,
            store=jobs,
            built_in_jobs=built_ins,
            command_runner=command_job_runner.CommandJobRunner(
                sandbox,
                self._configuration.sandbox.command_timeout_seconds,
            ),
            subagent_runner=subagents,
        )

    def _turn_runner(
        self,
        desk_configuration: agent_configuration.DeskConfiguration,
        executor: tool_call_executor.ToolCallExecutor,
        store: session_store.SessionStore,
    ) -> turn_runner.TurnRunner:
        """Builds a model router over every backend in the desk's order.

        Args:
            desk_configuration (agent_configuration.DeskConfiguration): The desk's settings.
            executor (tool_call_executor.ToolCallExecutor): The desk's tool executor, shared by every backend.
            store (session_store.SessionStore): Where the router keeps the desk's sessions.

        Returns:
            turn_runner.TurnRunner: The router, or a no-model runner when the desk names no backend.
        """
        routes = []
        for backend_name in desk_configuration.backend_order:
            backend_configuration = self._configuration.backends[backend_name]
            runner = self.backend_runner(
                desk_configuration,
                backend_name,
                backend_configuration,
                executor,
                self._prompt_builder(desk_configuration),
                self._configuration.agent.maximum_rounds,
                self._steering_inboxes[desk_configuration.name],
            )
            routes.append(model_router.BackendRoute(backend_name, runner))
        if not routes:
            _LOGGER.warning(
                'Desk %s has no backend; it will answer without a model',
                desk_configuration.name,
            )
            return no_model_turn_runner.NoModelTurnRunner()
        return model_router.ModelRouter(
            desk_configuration.name,
            routes,
            self._event_bus,
            session_store=store,
        )

    def backend_runner(
        self,
        desk_configuration: agent_configuration.DeskConfiguration,
        backend_name: str,
        backend_configuration: agent_configuration.BackendConfiguration,
        executor: tool_call_executor.ToolCallExecutor,
        prompt: prompt_builder.PromptBuilder,
        maximum_rounds: int,
        steering_inbox: steering_inbox_module.SteeringInbox | None = None,
    ) -> turn_runner.TurnRunner:
        """Builds the turn runner for one backend, according to its kind.

        The desk's own runners and its subagents' runners are both built here.

        Args:
            desk_configuration (agent_configuration.DeskConfiguration): The desk's settings.
            backend_name (str): The backend's name in trading_agent.toml.
            backend_configuration (agent_configuration.BackendConfiguration): Its settings.
            executor (tool_call_executor.ToolCallExecutor): The tool executor the runner calls tools through.
            prompt (prompt_builder.PromptBuilder): Builds the instructions; anything with a build() method returning a SystemPrompt.
            maximum_rounds (int): The most model calls one turn may make.
            steering_inbox (steering_inbox_module.SteeringInbox | None): The desk's mid-turn messages, for the desk's own runners; None for a subagent's.

        Returns:
            turn_runner.TurnRunner: The runner.
        """
        if backend_configuration.kind == 'claude_code':
            return self._claude_code_runner(
                desk_configuration,
                backend_name,
                backend_configuration,
                executor,
                prompt,
                maximum_rounds,
                steering_inbox,
            )
        if backend_configuration.kind == 'openai_compatible':
            model_backend = openai_compatible_backend.OpenAICompatibleBackend(
                backend_name,
                backend_configuration,
                self._secrets.openai_api_key,
            )
        else:
            model_backend = ollama_backend.OllamaBackend(
                backend_name,
                backend_configuration,
            )
        return self._agent_loop_runner(
            desk_configuration,
            model_backend,
            backend_configuration,
            executor,
            prompt,
            maximum_rounds,
            steering_inbox,
        )

    def _executor(
        self,
        desk_configuration: agent_configuration.DeskConfiguration,
        checkpoints: checkpoints_module.Checkpoints,
        sandbox: bash_sandbox.BashSandbox,
        library: skill_library.SkillLibrary,
        writer: skill_writer.SkillWriter,
        jobs: cron_job_store.CronJobStore,
        built_ins: list[cron_job.CronJob],
        alerts: price_alert_store.PriceAlertStore,
    ) -> tool_call_executor.ToolCallExecutor:
        """Builds the desk's tools and the executor that runs them.

        Args:
            desk_configuration (agent_configuration.DeskConfiguration): The desk's settings.
            checkpoints (checkpoints_module.Checkpoints): Snapshots the desk's files before the file tools change them.
            sandbox (bash_sandbox.BashSandbox): The desk's bash sandbox.
            library (skill_library.SkillLibrary): The desk's skills, for load_skill.
            writer (skill_writer.SkillWriter): Changes the desk's own skills.
            jobs (cron_job_store.CronJobStore): The desk's scheduled jobs.
            built_ins (list[cron_job.CronJob]): The desk's heartbeat and rollover jobs.
            alerts (price_alert_store.PriceAlertStore): The desk's price alerts.

        Returns:
            tool_call_executor.ToolCallExecutor: The executor.
        """
        agent_settings = self._configuration.agent
        sandbox_settings = self._configuration.sandbox
        web_settings = self._configuration.web
        session = bash_session.BashSession(
            sandbox,
            sandbox_settings.command_timeout_seconds,
            sandbox_settings.maximum_output_characters,
        )
        desk_directory = self._layout.desk_directory(desk_configuration.name)
        policy = path_policy.PathPolicy(
            desk_directory,
            sandbox.hidden_paths(),
        )
        browser = browser_session.BrowserSession(
            desk_directory / 'browser_profile',
            self._layout.scratch_directory(desk_configuration.name)
            / 'screenshots',
            address_guard.AddressGuard(),
            self._configuration.browser,
        )
        tools = [
            get_time_tool.GetTimeTool(),
            propose_file_change_tool.ProposeFileChangeTool(
                self._proposal_store,
                desk_configuration.name,
            ),
            bash_run_tool.BashRunTool(session),
            bash_restart_tool.BashRestartTool(session),
            bash_background_tool.BashBackgroundTool(session),
            bash_check_tool.BashCheckTool(session),
            read_file_tool.ReadFileTool(policy),
            write_file_tool.WriteFileTool(policy, checkpoints),
            edit_file_tool.EditFileTool(policy, checkpoints),
            add_note_tool.AddNoteTool(
                self._layout.notes_directory(desk_configuration.name),
                checkpoints,
            ),
            search_sessions_tool.SearchSessionsTool(
                session_search.SessionSearch(desk_directory)
            ),
            load_skill_tool.LoadSkillTool(library),
            search_knowledge_tool.SearchKnowledgeTool(self._knowledge_base),
            cron_create_tool.CronCreateTool(jobs, self.calendar, self.hours),
            cron_list_tool.CronListTool(
                jobs,
                built_ins,
                self.calendar,
                self.hours,
            ),
            cron_delete_tool.CronDeleteTool(jobs),
            schedule_wakeup_tool.ScheduleWakeupTool(jobs),
            set_price_alert_tool.SetPriceAlertTool(self._broker_reader, alerts),
            cancel_price_alert_tool.CancelPriceAlertTool(alerts),
            send_message_tool.SendMessageTool(
                self._event_bus,
                desk_configuration.name,
            ),
            skill_create_tool.SkillCreateTool(writer),
            skill_patch_tool.SkillPatchTool(writer),
            skill_archive_tool.SkillArchiveTool(writer),
            web_search_tool.WebSearchTool(
                web_settings.searxng_base_url,
                web_settings.search_result_limit,
            ),
            web_fetch_tool.WebFetchTool(
                web_settings.fetch_timeout_seconds,
                web_settings.maximum_page_characters,
            ),
            browser_open_tool.BrowserOpenTool(browser),
            browser_snapshot_tool.BrowserSnapshotTool(browser),
            browser_click_tool.BrowserClickTool(browser),
            browser_type_tool.BrowserTypeTool(browser),
            browser_screenshot_tool.BrowserScreenshotTool(
                browser,
                desk_directory,
            ),
            browser_back_tool.BrowserBackTool(browser),
            browser_tabs_tool.BrowserTabsTool(browser),
            search_instruments_tool.SearchInstrumentsTool(
                self._broker_reader,
                self._result_formatter,
            ),
            get_quote_tool.GetQuoteTool(
                self._broker_reader,
                self._result_formatter,
            ),
            get_candles_tool.GetCandlesTool(
                self._broker_reader,
                self._result_formatter,
            ),
            get_portfolio_tool.GetPortfolioTool(
                self._broker_reader,
                self._result_formatter,
            ),
            get_orders_tool.GetOrdersTool(
                self._broker_reader,
                self._result_formatter,
            ),
            place_order_tool.PlaceOrderTool(
                self._order_services,
                desk_configuration.name,
                self._configuration.mode,
            ),
            place_bracket_order_tool.PlaceBracketOrderTool(
                self._order_services,
                desk_configuration.name,
                self._configuration.mode,
            ),
            modify_order_tool.ModifyOrderTool(
                self._order_services,
                desk_configuration.name,
                self._configuration.mode,
            ),
            cancel_order_tool.CancelOrderTool(
                self._order_services,
                desk_configuration.name,
                self._configuration.mode,
            ),
            flatten_desk_tool.FlattenDeskTool(
                self._order_services,
                desk_configuration.name,
                self._configuration.mode,
            ),
        ]
        if self._mcp_manager is not None and self._mcp_manager.connections:
            tools.append(tool_search_tool.ToolSearchTool(self._mcp_manager))
            tools.append(call_mcp_tool_tool.CallMcpToolTool(self._mcp_manager))
        subagents = self._subagent_runner(desk_configuration, sandbox, tools)
        tools.append(delegate_task_tool.DelegateTaskTool(subagents))
        self._schedule_parts[desk_configuration.name] = (
            jobs,
            built_ins,
            sandbox,
            subagents,
        )
        registry = tool_registry.ToolRegistry(
            tools,
            timeout_seconds=agent_settings.tool_timeout_seconds,
        )
        return tool_call_executor.ToolCallExecutor(
            desk_configuration.name,
            registry,
            self._event_bus,
            loop_guard.LoopGuard(agent_settings.maximum_identical_tool_calls),
        )

    def _subagent_runner(
        self,
        desk_configuration: agent_configuration.DeskConfiguration,
        sandbox: bash_sandbox.BashSandbox,
        desk_tools: list,
    ) -> subagent_runner.SubagentRunner:
        """Builds the runner that carries out the desk's delegated tasks.

        Args:
            desk_configuration (agent_configuration.DeskConfiguration): The desk's settings.
            sandbox (bash_sandbox.BashSandbox): The desk's sandbox, in which each task gets a fresh bash session.
            desk_tools (list): The desk's tools, which subagents share; delegate_task is not among them yet, so it can never be given to a subagent.

        Returns:
            subagent_runner.SubagentRunner: The runner.
        """
        agent_settings = self._configuration.agent
        sandbox_settings = self._configuration.sandbox
        toolbox = subagent_toolbox.SubagentToolbox(
            list(desk_tools),
            functools.partial(
                bash_session.BashSession,
                sandbox,
                sandbox_settings.command_timeout_seconds,
                sandbox_settings.maximum_output_characters,
            ),
            agent_settings.tool_timeout_seconds,
        )
        return subagent_runner.SubagentRunner(
            desk_configuration.name,
            self._configuration.mode,
            self._subagent_library,
            toolbox,
            functools.partial(self.backend_runner, desk_configuration),
            desk_configuration.backend_order,
            self._configuration.backends,
            self._event_bus,
            agent_settings.maximum_identical_tool_calls,
        )

    def _claude_code_runner(
        self,
        desk_configuration: agent_configuration.DeskConfiguration,
        backend_name: str,
        backend_configuration: agent_configuration.BackendConfiguration,
        executor: tool_call_executor.ToolCallExecutor,
        prompt: prompt_builder.PromptBuilder,
        maximum_rounds: int,
        steering_inbox: steering_inbox_module.SteeringInbox | None = None,
    ) -> claude_code_turn_runner.ClaudeCodeTurnRunner:
        """Builds a Claude Code session for a desk or one of its subagents.

        Args:
            desk_configuration (agent_configuration.DeskConfiguration): The desk's settings.
            backend_name (str): The backend's name in trading_agent.toml.
            backend_configuration (agent_configuration.BackendConfiguration): Its settings.
            executor (tool_call_executor.ToolCallExecutor): The tool executor.
            prompt (prompt_builder.PromptBuilder): Builds the instructions.
            maximum_rounds (int): The most model calls one turn may make.
            steering_inbox (steering_inbox_module.SteeringInbox | None): The desk's mid-turn messages, for the desk's own runners; None for a subagent's.

        Returns:
            claude_code_turn_runner.ClaudeCodeTurnRunner: The runner.
        """
        working_directory = self._layout.scratch_directory(
            desk_configuration.name
        )
        settings = claude_code_turn_runner.ClaudeCodeSettings(
            prompt_builder=prompt,
            oauth_token=self._secrets.claude_code_oauth_token,
            working_directory=working_directory.resolve(),
            maximum_rounds=maximum_rounds,
            sessions_directory=self._claude_sessions_directory(),
            compression_threshold=self._configuration.agent.compression_threshold,
            emergency_compression_threshold=self._configuration.agent.emergency_compression_threshold,
        )
        return claude_code_turn_runner.ClaudeCodeTurnRunner(
            desk_configuration.name,
            backend_name,
            backend_configuration,
            claude_tool_bridge.ClaudeToolBridge(executor),
            self._event_bus,
            settings,
            steering_inbox,
        )

    def _claude_sessions_directory(self) -> Path:
        """Where Claude Code keeps its session files.

        Returns:
            Path: The projects folder inside CLAUDE_CONFIG_DIR, or inside ~/.claude when that is not set.
        """
        configuration_directory = os.environ.get('CLAUDE_CONFIG_DIR')
        if configuration_directory:
            return Path(configuration_directory) / 'projects'
        return Path.home() / '.claude' / 'projects'

    def _agent_loop_runner(
        self,
        desk_configuration: agent_configuration.DeskConfiguration,
        model_backend: backend_module.ModelBackend,
        backend_configuration: agent_configuration.BackendConfiguration,
        executor: tool_call_executor.ToolCallExecutor,
        prompt: prompt_builder.PromptBuilder,
        maximum_rounds: int,
        steering_inbox: steering_inbox_module.SteeringInbox | None = None,
    ) -> agent_turn_runner.AgentTurnRunner:
        """Builds an agent loop, with its own conversation and compressor, on a model backend.

        Args:
            desk_configuration (agent_configuration.DeskConfiguration): The desk's settings.
            model_backend (backend_module.ModelBackend): The model the loop asks.
            backend_configuration (agent_configuration.BackendConfiguration): Its settings, for the context window.
            executor (tool_call_executor.ToolCallExecutor): The tool executor.
            prompt (prompt_builder.PromptBuilder): Builds the instructions.
            maximum_rounds (int): The most model calls one turn may make.
            steering_inbox (steering_inbox_module.SteeringInbox | None): The desk's mid-turn messages, for the desk's own runners; None for a subagent's.

        Returns:
            agent_turn_runner.AgentTurnRunner: The runner.
        """
        agent_settings = self._configuration.agent
        compressor = context_compressor.ContextCompressor(
            desk_configuration.name,
            backend_configuration.context_window,
            agent_settings.compression_threshold,
            agent_settings.emergency_compression_threshold,
            self._event_bus,
        )
        loop = agent_loop.AgentLoop(
            desk_configuration.name,
            model_backend,
            executor,
            self._event_bus,
            maximum_rounds,
            compressor,
            steering_inbox,
        )
        return agent_turn_runner.AgentTurnRunner(loop, prompt)

    def _prompt_builder(
        self,
        desk_configuration: agent_configuration.DeskConfiguration,
    ) -> prompt_builder.PromptBuilder:
        """Builds the prompt builder for a desk, with the skill library build() made for it.

        Args:
            desk_configuration (agent_configuration.DeskConfiguration): The desk's settings.

        Returns:
            prompt_builder.PromptBuilder: The builder.
        """
        return prompt_builder.PromptBuilder(
            self._layout,
            desk_configuration.name,
            self._configuration.mode,
            self._skill_libraries.get(desk_configuration.name),
            self._mcp_manager,
            self._subagent_library,
            self._other_desk_names(desk_configuration.name),
        )

    def _other_desk_names(self, desk_name: str) -> list[str]:
        """The enabled desks other than one.

        Args:
            desk_name (str): The desk to leave out.

        Returns:
            list[str]: The other enabled desks' names, in configuration order.
        """
        names = []
        for desk in self._configuration.desks:
            if desk.enabled and desk.name != desk_name:
                names.append(desk.name)
        return names
