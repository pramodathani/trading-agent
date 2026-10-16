"""Builds one desk with its tools, model backend and agent loop.

Each milestone adds parts to a desk, so this one class is where they are put together. In milestone 2 a desk uses the first backend in its backend_order; the model router (milestone 4) will try the others in turn.

Typical usage example:

  desk = DeskBuilder(configuration, event_bus).build(desk_configuration)
"""

import logging

from trading_agent.agent import agent_loop
from trading_agent.agent import agent_turn_runner
from trading_agent.agent import loop_guard
from trading_agent.backends import backend as backend_module
from trading_agent.backends import ollama_backend
from trading_agent.configuration import agent_configuration
from trading_agent.runtime import desk_runtime
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import no_model_turn_runner
from trading_agent.runtime import turn_runner
from trading_agent.tools import get_time_tool
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
        event_bus: event_bus_module.EventBus,
    ):
        """Creates the builder.

        Args:
            configuration (agent_configuration.AgentConfiguration): The agent's configuration.
            event_bus (event_bus_module.EventBus): The bus every desk publishes on.
        """
        self._configuration = configuration
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
        """Builds the agent loop for a desk, or a no-model runner if it has no usable backend.

        Args:
            desk_configuration (agent_configuration.DeskConfiguration): The desk's settings.

        Returns:
            turn_runner.TurnRunner: The runner for the desk's turns.
        """
        backend = self._first_backend(desk_configuration)
        if backend is None:
            _LOGGER.warning(
                'Desk %s has no usable backend; it will answer without a model',
                desk_configuration.name,
            )
            return no_model_turn_runner.NoModelTurnRunner()
        agent_settings = self._configuration.agent
        registry = tool_registry.ToolRegistry(
            [
                get_time_tool.GetTimeTool(),
            ],
            timeout_seconds=agent_settings.tool_timeout_seconds,
        )
        loop = agent_loop.AgentLoop(
            desk_configuration.name,
            backend,
            registry,
            self._event_bus,
            loop_guard.LoopGuard(agent_settings.maximum_identical_tool_calls),
            agent_settings.maximum_rounds,
        )
        return agent_turn_runner.AgentTurnRunner(loop, _BASIC_SYSTEM_PROMPT)

    def _first_backend(
        self,
        desk_configuration: agent_configuration.DeskConfiguration,
    ) -> backend_module.ModelBackend | None:
        """Builds the first backend in the desk's order that this milestone can drive.

        Args:
            desk_configuration (agent_configuration.DeskConfiguration): The desk's settings.

        Returns:
            backend_module.ModelBackend | None: The backend, or None when the desk names no Ollama backend.
        """
        for backend_name in desk_configuration.backend_order:
            backend_configuration = self._configuration.backends[backend_name]
            if backend_configuration.kind == 'ollama':
                return ollama_backend.OllamaBackend(
                    backend_name,
                    backend_configuration,
                )
        return None
