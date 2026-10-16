"""Builds one desk with its tools, model backend and turn runner.

Each milestone adds parts to a desk, so this one class is where they are put together. Every backend in the desk's backend_order becomes a route of the desk's model router, most preferred first.

Typical usage example:

  desk = DeskBuilder(configuration, secrets, event_bus).build(desk_configuration)
"""

import logging

from trading_agent.agent import agent_loop
from trading_agent.agent import agent_turn_runner
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
from trading_agent.runtime import desk_runtime
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import no_model_turn_runner
from trading_agent.runtime import turn_runner
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
from trading_agent.tools import edit_file_tool
from trading_agent.tools import get_candles_tool
from trading_agent.tools import get_orders_tool
from trading_agent.tools import get_portfolio_tool
from trading_agent.tools import get_quote_tool
from trading_agent.tools import get_time_tool
from trading_agent.tools import path_policy
from trading_agent.tools import propose_file_change_tool
from trading_agent.tools import read_file_tool
from trading_agent.tools import search_instruments_tool
from trading_agent.tools import tool_call_executor
from trading_agent.tools import tool_registry
from trading_agent.tools import web_fetch_tool
from trading_agent.tools import web_search_tool
from trading_agent.tools import write_file_tool
from trading_agent.trading import broker_reader
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
    ):
        """Creates the builder.

        Args:
            configuration (agent_configuration.AgentConfiguration): The agent's configuration.
            secrets (secrets_module.Secrets): The secrets read from the environment and .env.
            event_bus (event_bus_module.EventBus): The bus every desk publishes on.
        """
        self._configuration = configuration
        self._secrets = secrets
        self._event_bus = event_bus
        self._layout = workspace_layout.WorkspaceLayout(
            configuration.workspace_directory
        )
        self._proposal_store = proposal_store.ProposalStore(self._layout)
        self._broker_reader = broker_reader.BrokerReader(
            configuration.tradingmachine_environment_file
        )
        self._result_formatter = result_formatter.ResultFormatter()

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
        executor = self._executor(desk_configuration)
        return desk_runtime.DeskRuntime(
            desk_configuration,
            self._event_bus,
            self._turn_runner(desk_configuration, executor),
            self._configuration.mode,
            executor.tool_registry,
        )

    def _turn_runner(
        self,
        desk_configuration: agent_configuration.DeskConfiguration,
        executor: tool_call_executor.ToolCallExecutor,
    ) -> turn_runner.TurnRunner:
        """Builds a model router over every backend in the desk's order.

        Args:
            desk_configuration (agent_configuration.DeskConfiguration): The desk's settings.
            executor (tool_call_executor.ToolCallExecutor): The desk's tool executor, shared by every backend.

        Returns:
            turn_runner.TurnRunner: The router, or a no-model runner when the desk names no backend.
        """
        routes = []
        for backend_name in desk_configuration.backend_order:
            backend_configuration = self._configuration.backends[backend_name]
            runner = self._backend_runner(
                desk_configuration,
                backend_name,
                backend_configuration,
                executor,
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
        )

    def _backend_runner(
        self,
        desk_configuration: agent_configuration.DeskConfiguration,
        backend_name: str,
        backend_configuration: agent_configuration.BackendConfiguration,
        executor: tool_call_executor.ToolCallExecutor,
    ) -> turn_runner.TurnRunner:
        """Builds the turn runner for one backend, according to its kind.

        Args:
            desk_configuration (agent_configuration.DeskConfiguration): The desk's settings.
            backend_name (str): The backend's name in trading_agent.toml.
            backend_configuration (agent_configuration.BackendConfiguration): Its settings.
            executor (tool_call_executor.ToolCallExecutor): The desk's tool executor.

        Returns:
            turn_runner.TurnRunner: The runner.
        """
        if backend_configuration.kind == 'claude_code':
            return self._claude_code_runner(
                desk_configuration,
                backend_name,
                backend_configuration,
                executor,
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
            executor,
        )

    def _executor(
        self,
        desk_configuration: agent_configuration.DeskConfiguration,
    ) -> tool_call_executor.ToolCallExecutor:
        """Builds the desk's tools and the executor that runs them.

        Args:
            desk_configuration (agent_configuration.DeskConfiguration): The desk's settings.

        Returns:
            tool_call_executor.ToolCallExecutor: The executor.
        """
        agent_settings = self._configuration.agent
        sandbox_settings = self._configuration.sandbox
        web_settings = self._configuration.web
        sandbox = bash_sandbox.BashSandbox(
            self._layout.scratch_directory(desk_configuration.name),
            sandbox_settings.hidden_paths,
        )
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
        registry = tool_registry.ToolRegistry(
            [
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
                write_file_tool.WriteFileTool(policy),
                edit_file_tool.EditFileTool(policy),
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
            ],
            timeout_seconds=agent_settings.tool_timeout_seconds,
        )
        return tool_call_executor.ToolCallExecutor(
            desk_configuration.name,
            registry,
            self._event_bus,
            loop_guard.LoopGuard(agent_settings.maximum_identical_tool_calls),
        )

    def _claude_code_runner(
        self,
        desk_configuration: agent_configuration.DeskConfiguration,
        backend_name: str,
        backend_configuration: agent_configuration.BackendConfiguration,
        executor: tool_call_executor.ToolCallExecutor,
    ) -> claude_code_turn_runner.ClaudeCodeTurnRunner:
        """Builds a desk's Claude Code session.

        Args:
            desk_configuration (agent_configuration.DeskConfiguration): The desk's settings.
            backend_name (str): The backend's name in trading_agent.toml.
            backend_configuration (agent_configuration.BackendConfiguration): Its settings.
            executor (tool_call_executor.ToolCallExecutor): The desk's tool executor.

        Returns:
            claude_code_turn_runner.ClaudeCodeTurnRunner: The runner.
        """
        working_directory = self._layout.scratch_directory(
            desk_configuration.name
        )
        settings = claude_code_turn_runner.ClaudeCodeSettings(
            prompt_builder=self._prompt_builder(desk_configuration),
            oauth_token=self._secrets.claude_code_oauth_token,
            working_directory=working_directory.resolve(),
            maximum_rounds=self._configuration.agent.maximum_rounds,
        )
        return claude_code_turn_runner.ClaudeCodeTurnRunner(
            desk_configuration.name,
            backend_name,
            backend_configuration,
            claude_tool_bridge.ClaudeToolBridge(executor),
            self._event_bus,
            settings,
        )

    def _agent_loop_runner(
        self,
        desk_configuration: agent_configuration.DeskConfiguration,
        model_backend: backend_module.ModelBackend,
        executor: tool_call_executor.ToolCallExecutor,
    ) -> agent_turn_runner.AgentTurnRunner:
        """Builds an agent loop, with its own conversation, on a model backend.

        Args:
            desk_configuration (agent_configuration.DeskConfiguration): The desk's settings.
            model_backend (backend_module.ModelBackend): The model the loop asks.
            executor (tool_call_executor.ToolCallExecutor): The desk's tool executor.

        Returns:
            agent_turn_runner.AgentTurnRunner: The runner.
        """
        loop = agent_loop.AgentLoop(
            desk_configuration.name,
            model_backend,
            executor,
            self._event_bus,
            self._configuration.agent.maximum_rounds,
        )
        return agent_turn_runner.AgentTurnRunner(
            loop,
            self._prompt_builder(desk_configuration),
        )

    def _prompt_builder(
        self,
        desk_configuration: agent_configuration.DeskConfiguration,
    ) -> prompt_builder.PromptBuilder:
        """Builds the prompt builder for a desk.

        Args:
            desk_configuration (agent_configuration.DeskConfiguration): The desk's settings.

        Returns:
            prompt_builder.PromptBuilder: The builder.
        """
        return prompt_builder.PromptBuilder(
            self._layout,
            desk_configuration.name,
            self._configuration.mode,
        )
