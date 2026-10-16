"""Builds one desk with its tools, model backend and turn runner.

Each milestone adds parts to a desk, so this one class is where they are put together. Every backend in the desk's backend_order becomes a route of the desk's model router, most preferred first.

Typical usage example:

  desk = DeskBuilder(configuration, secrets, event_bus).build(desk_configuration)
"""

import logging

from trading_agent.agent import agent_loop
from trading_agent.agent import agent_turn_runner
from trading_agent.agent import loop_guard
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
from trading_agent.tools import get_time_tool
from trading_agent.tools import tool_call_executor
from trading_agent.tools import tool_registry

_LOGGER = logging.getLogger(__name__)

_BASIC_SYSTEM_PROMPT = '\n'.join(
    [
        'You are a trading desk inside trading-agent, an AI agent that trades Indian markets through the tradingmachine library.',
        'Use your tools whenever they can give you a fact you would otherwise have to guess, such as the current time.',
        'Answer briefly and plainly.',
    ]
)


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
        return desk_runtime.DeskRuntime(
            desk_configuration,
            self._event_bus,
            self._turn_runner(desk_configuration),
        )

    def _turn_runner(
        self,
        desk_configuration: agent_configuration.DeskConfiguration,
    ) -> turn_runner.TurnRunner:
        """Builds a model router over every backend in the desk's order.

        Args:
            desk_configuration (agent_configuration.DeskConfiguration): The desk's settings.

        Returns:
            turn_runner.TurnRunner: The router, or a no-model runner when the desk names no backend.
        """
        executor = self._executor(desk_configuration)
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
        registry = tool_registry.ToolRegistry(
            [
                get_time_tool.GetTimeTool(),
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
        working_directory = (
            self._configuration.workspace_directory
            / 'desks'
            / desk_configuration.name
            / 'scratch'
        )
        settings = claude_code_turn_runner.ClaudeCodeSettings(
            system_prompt=_BASIC_SYSTEM_PROMPT,
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
        return agent_turn_runner.AgentTurnRunner(loop, _BASIC_SYSTEM_PROMPT)
