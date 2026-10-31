"""Runs the tasks a trader delegates to its subagents.

Each task gets a fresh model router over the subagent's backends (or the trader's, for "inherit"), its own tool registry from the toolbox, and a system prompt built from its definition. Tasks run side by side; each has its own time limit, and one that fails, times out or crashes never stops the others. Afterwards the task's bash session and any Claude Code process are closed.

Every task publishes subagent_started and subagent_finished, and its tool calls carry the task's trigger id, so the journal shows what each subagent did.

Typical usage example:

  runner = SubagentRunner(trader_name, mode, library, toolbox, runner_factory, ['claude', 'qwen'], backends, event_bus, 3)
  reports = await runner.run_all([SubagentTask('news_reader', 'What moved INFY today?')])
"""

import asyncio
import dataclasses
import logging
import time
from collections.abc import Callable, Mapping, Sequence

from trading_agent.agent import loop_guard
from trading_agent.backends import backend as backend_module
from trading_agent.backends import model_router
from trading_agent.configuration import agent_configuration
from trading_agent.requests import permission_gate as permission_gate_module
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.runtime import turn_runner
from trading_agent.subagents import subagent_definition as definition_module
from trading_agent.subagents import subagent_library as subagent_library_module
from trading_agent.subagents import subagent_prompt_builder
from trading_agent.subagents import subagent_toolbox as subagent_toolbox_module
from trading_agent.tools import tool_call_executor

_LOGGER = logging.getLogger(__name__)
CLAUDE_ALIASES = (
    'opus',
    'sonnet',
    'haiku',
    'fable',
)
RunnerFactory = Callable[
    [
        str,
        agent_configuration.BackendConfiguration,
        tool_call_executor.ToolCallExecutor,
        subagent_prompt_builder.SubagentPromptBuilder,
        int,
    ],
    turn_runner.TurnRunner,
]


@dataclasses.dataclass(frozen=True)
class SubagentTask:
    """One task for one subagent.

    Attributes:
        subagent: The subagent's name.
        task: What it should do, with everything it needs to know.
    """

    subagent: str
    task: str


@dataclasses.dataclass(frozen=True)
class SubagentReport:
    """How one task ended.

    Attributes:
        subagent: The subagent's name.
        outcome: "answered", "timed out", "failed" or "unknown subagent".
        text: The subagent's report, or why there is none.
        backend_name: The backend that answered, or None.
        seconds: How long the task took.
        notes: Remarks about the definition, such as tools it may not have.
    """

    subagent: str
    outcome: str
    text: str
    backend_name: str | None
    seconds: float
    notes: tuple[str, ...]


class SubagentRunner:
    """Runs one trader's subagent tasks."""

    def __init__(
        self,
        trader_name: str,
        mode: str,
        library: subagent_library_module.SubagentLibrary,
        toolbox: subagent_toolbox_module.SubagentToolbox,
        runner_factory: RunnerFactory,
        trader_backend_order: Sequence[str],
        backends: Mapping[str, agent_configuration.BackendConfiguration],
        event_bus: event_bus_module.EventBus,
        maximum_identical_tool_calls: int,
        permission_gate: permission_gate_module.PermissionGate | None = None,
    ):
        """Creates the runner.

        Args:
            trader_name (str): The trader the subagents work for.
            mode (str): "dry_run" or "live".
            library (subagent_library_module.SubagentLibrary): The definitions.
            toolbox (subagent_toolbox_module.SubagentToolbox): Builds each task's tools.
            runner_factory (RunnerFactory): Builds a turn runner from a backend name, its settings, an executor, a prompt builder and a round limit.
            trader_backend_order (Sequence[str]): The trader's backends, for subagents that inherit them.
            backends (Mapping[str, agent_configuration.BackendConfiguration]): Every configured backend.
            event_bus (event_bus_module.EventBus): Where each task's events are published.
            maximum_identical_tool_calls (int): The loop guard's limit for each task.
            permission_gate (permission_gate_module.PermissionGate | None): Holds the tasks' calls that need the user's permission, or None when none do.
        """
        self._trader_name = trader_name
        self._mode = mode
        self._library = library
        self._toolbox = toolbox
        self._runner_factory = runner_factory
        self._trader_backend_order = list(trader_backend_order)
        self._backends = backends
        self._event_bus = event_bus
        self._maximum_identical_tool_calls = maximum_identical_tool_calls
        self._permission_gate = permission_gate

    async def run_all(
        self,
        tasks: Sequence[SubagentTask],
    ) -> list[SubagentReport]:
        """Runs the tasks side by side.

        Args:
            tasks (Sequence[SubagentTask]): The tasks.

        Returns:
            list[SubagentReport]: One report per task, in the order given.
        """
        return list(
            await asyncio.gather(*[self.run_one(task) for task in tasks])
        )

    async def run_one(self, task: SubagentTask) -> SubagentReport:
        """Runs one task from start to finish.

        Args:
            task (SubagentTask): The task.

        Returns:
            SubagentReport: How it ended.
        """
        started = time.monotonic()
        definition = self._library.find(task.subagent)
        if definition is None:
            names = []
            for known in self._library.definitions():
                names.append(known.name)
            return SubagentReport(
                subagent=task.subagent,
                outcome='unknown subagent',
                text=f'There is no subagent named {task.subagent}. Subagents: {", ".join(names) or "none"}.',
                backend_name=None,
                seconds=0.0,
                notes=(),
            )
        notes = []
        routes_wanted = self._backend_choices(definition, notes)
        prepared = self._toolbox.prepare(definition)
        for name in prepared.refused:
            notes.append(f'{name} is never given to subagents')
        for name in prepared.unknown:
            notes.append(f"{name} is not one of the trader's tools")
        executor = tool_call_executor.ToolCallExecutor(
            self._trader_name,
            prepared.registry,
            self._event_bus,
            loop_guard.LoopGuard(self._maximum_identical_tool_calls),
            self._permission_gate,
        )
        prompt = subagent_prompt_builder.SubagentPromptBuilder(
            definition,
            self._trader_name,
            self._mode,
        )
        routes = []
        for backend_name, backend_configuration in routes_wanted:
            runner = self._runner_factory(
                backend_name,
                backend_configuration,
                executor,
                prompt,
                definition.maximum_turns,
            )
            routes.append(model_router.BackendRoute(backend_name, runner))
        trigger = trigger_module.Trigger.now(
            trigger_module.TriggerSource.SUBAGENT,
            self._trader_name,
            f'[Task from the {self._trader_name} trader]\n{task.task}',
        )
        self._publish(
            event_module.EventKind.SUBAGENT_STARTED,
            {
                'trigger_id': trigger.trigger_id,
                'subagent': definition.name,
                'task': task.task,
                'backends': [name for name, _ in routes_wanted],
                'tools': prepared.registry.tool_names,
            },
        )
        outcome, text, backend_name = await self._run(
            routes, trigger, definition, executor
        )
        if prepared.bash_session is not None:
            await prepared.bash_session.close()
        report = SubagentReport(
            subagent=definition.name,
            outcome=outcome,
            text=text,
            backend_name=backend_name,
            seconds=time.monotonic() - started,
            notes=tuple(notes),
        )
        self._publish(
            event_module.EventKind.SUBAGENT_FINISHED,
            {
                'trigger_id': trigger.trigger_id,
                'subagent': definition.name,
                'outcome': outcome,
                'backend': backend_name,
                'seconds': round(report.seconds, 1),
                'report_characters': len(text),
            },
        )
        return report

    async def _run(
        self,
        routes: list[model_router.BackendRoute],
        trigger: trigger_module.Trigger,
        definition: definition_module.SubagentDefinition,
        executor: tool_call_executor.ToolCallExecutor,
    ) -> tuple[str, str, str | None]:
        """Runs the task's turn with its time limit, and always closes its runners.

        Args:
            routes (list[model_router.BackendRoute]): The task's backends.
            trigger (trigger_module.Trigger): The task.
            definition (definition_module.SubagentDefinition): The subagent, for its time limit.
            executor (tool_call_executor.ToolCallExecutor): The task's executor, whose record of calls keeps a backend taking over from repeating them.

        Returns:
            tuple[str, str, str | None]: A tuple (outcome, text, backend_name), where outcome is "answered", "timed out" or "failed", text the report or the reason, and backend_name the backend that answered, if any.
        """
        router = model_router.ModelRouter(
            self._trader_name,
            routes,
            self._event_bus,
            completed_calls=executor.completed_calls,
        )
        try:
            result = await asyncio.wait_for(
                router.run_turn(trigger),
                definition.timeout_seconds,
            )
        except TimeoutError:
            return (
                'timed out',
                f'Stopped after {definition.timeout_seconds} seconds without a report.',
                None,
            )
        except backend_module.BackendUnavailableError as error:
            return 'failed', str(error), None
        except Exception as error:
            _LOGGER.exception('Subagent %s crashed', definition.name)
            return 'failed', f'The task crashed: {error!r}', None
        finally:
            await router.close()
        return 'answered', result.text, router.last_backend_name

    def _backend_choices(
        self,
        definition: definition_module.SubagentDefinition,
        notes: list[str],
    ) -> list[tuple[str, agent_configuration.BackendConfiguration]]:
        """Turns the definition's model field into backends.

        Args:
            definition (definition_module.SubagentDefinition): The subagent.
            notes (list[str]): Gains a remark for each model name that matches nothing.

        Returns:
            list[tuple[str, agent_configuration.BackendConfiguration]]: Tuples (name, settings), most preferred first; the trader's own order when the definition names no usable model.
        """
        choices = []
        if definition.models is not None:
            for model in definition.models:
                choice = self._backend_for(model)
                if choice is None:
                    notes.append(f'model {model} matches no backend')
                    continue
                choices.append(choice)
        if choices:
            return choices
        for name in self._trader_backend_order:
            choices.append((name, self._backends[name]))
        return choices

    def _backend_for(
        self,
        model: str,
    ) -> tuple[str, agent_configuration.BackendConfiguration] | None:
        """Finds the backend for one model name.

        Args:
            model (str): A backend name, or a Claude alias such as sonnet.

        Returns:
            tuple[str, agent_configuration.BackendConfiguration] | None: The backend's name and settings, with the Claude model replaced for an alias, or None when nothing matches.
        """
        if model in self._backends:
            return model, self._backends[model]
        if model not in CLAUDE_ALIASES:
            return None
        for name, configuration in self._backends.items():
            if configuration.kind == 'claude_code':
                return name, configuration.model_copy(
                    update={
                        'model': model,
                    }
                )
        return None

    def _publish(self, kind: event_module.EventKind, payload: dict) -> None:
        """Publishes an event from the trader.

        Args:
            kind (event_module.EventKind): What happened.
            payload (dict): The event's details.
        """
        self._event_bus.publish(
            event_module.Event.now(kind, self._trader_name, payload)
        )
