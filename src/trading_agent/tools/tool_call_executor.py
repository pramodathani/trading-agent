"""Runs one tool call the same way for every backend.

Whether the call comes from the agent loop (Gemma, Qwen, OpenAI) or from Claude Code, it is published, checked by the loop guard and the permission gate, run through the registry, and its result published. Keeping that in one place means every backend gets the same protections.

Typical usage example:

  executor = ToolCallExecutor('main', registry, event_bus, loop_guard)
  executor.start_turn()
  result = await executor.execute(trigger, call)
"""

import dataclasses
from typing import Any

from trading_agent.agent import loop_guard as loop_guard_module
from trading_agent.agent import messages
from trading_agent.requests import permission_gate as permission_gate_module
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.tools import tool as tool_module
from trading_agent.tools import tool_registry as tool_registry_module

_REMEMBERED_TRIGGERS = 50


@dataclasses.dataclass(frozen=True)
class CompletedCall:
    """A tool call that ran, or was held for permission, during a turn.

    Attributes:
        name: The tool.
        arguments: The arguments it was called with.
        result_text: What it returned.
        is_error: Whether it failed.
    """

    name: str
    arguments: dict[str, Any]
    result_text: str
    is_error: bool


class ToolCallExecutor:
    """Runs a trader's tool calls through the loop guard and the registry.

    Attributes:
        tool_registry: The trader's tools.
    """

    def __init__(
        self,
        trader_name: str,
        tool_registry: tool_registry_module.ToolRegistry,
        event_bus: event_bus_module.EventBus,
        loop_guard: loop_guard_module.LoopGuard,
        permission_gate: permission_gate_module.PermissionGate | None = None,
    ):
        """Creates the executor.

        Args:
            trader_name (str): The trader the calls belong to, used to tag events.
            tool_registry (tool_registry_module.ToolRegistry): The trader's tools.
            event_bus (event_bus_module.EventBus): Where calls and results are published.
            loop_guard (loop_guard_module.LoopGuard): The guard against repeated identical calls.
            permission_gate (permission_gate_module.PermissionGate | None): Holds calls that need the user's permission, or None when none do.
        """
        self._trader_name = trader_name
        self._permission_gate = permission_gate
        self._completed: dict[str, list[CompletedCall]] = {}
        self.tool_registry = tool_registry
        self._event_bus = event_bus
        self._loop_guard = loop_guard

    def start_turn(self) -> None:
        """Resets the loop guard at the start of a turn."""
        self._loop_guard.start_turn()

    async def execute(
        self,
        trigger: trigger_module.Trigger,
        call: messages.ToolCall,
    ) -> tool_module.ToolResult:
        """Publishes a call, runs it unless the guard refuses it, and publishes the result.

        Args:
            trigger (trigger_module.Trigger): The trigger of the current turn.
            call (messages.ToolCall): The call to run.

        Returns:
            tool_module.ToolResult: The tool's result, the guard's refusal, or a note that the call waits for the user's permission.
        """
        self._publish(
            event_module.EventKind.TOOL_CALL,
            {
                'trigger_id': trigger.trigger_id,
                'call_id': call.call_id,
                'name': call.name,
                'arguments': call.arguments,
            },
        )
        gate = self._permission_gate
        if not self._loop_guard.allows(call):
            result = tool_module.ToolResult.error(
                self._loop_guard.refusal_text(call)
            )
        elif gate is not None and gate.needs_permission(
            self._trader_name, call.name
        ):
            result = gate.hold(self._trader_name, call)
        else:
            result = await self.tool_registry.run(call)
        self._remember(trigger.trigger_id, call, result)
        payload = {
            'trigger_id': trigger.trigger_id,
            'call_id': call.call_id,
            'name': call.name,
            'is_error': result.is_error,
            'text': result.text,
        }
        if result.picture_trader_path is not None:
            payload['picture_path'] = result.picture_trader_path
        self._publish(event_module.EventKind.TOOL_RESULT, payload)
        return result

    def completed_calls(self, trigger_id: str) -> list[CompletedCall]:
        """The calls that ran, or were held for permission, for one trigger, oldest first.

        The model router reads them when a backend fails partway through a turn, so the next backend does not repeat them.

        Args:
            trigger_id (str): The trigger.

        Returns:
            list[CompletedCall]: The calls; empty when none ran or the trigger is too old to be remembered.
        """
        return list(self._completed.get(trigger_id, []))

    def _remember(
        self,
        trigger_id: str,
        call: messages.ToolCall,
        result: tool_module.ToolResult,
    ) -> None:
        """Records a call for its trigger, forgetting the oldest triggers beyond a limit.

        Args:
            trigger_id (str): The trigger.
            call (messages.ToolCall): The call.
            result (tool_module.ToolResult): What it returned.
        """
        if (
            trigger_id not in self._completed
            and len(self._completed) >= _REMEMBERED_TRIGGERS
        ):
            oldest = next(iter(self._completed))
            del self._completed[oldest]
        self._completed.setdefault(trigger_id, []).append(
            CompletedCall(
                name=call.name,
                arguments=call.arguments,
                result_text=result.text,
                is_error=result.is_error,
            )
        )

    def _publish(self, kind: event_module.EventKind, payload: dict) -> None:
        """Publishes an event from this trader.

        Args:
            kind (event_module.EventKind): What happened.
            payload (dict): The event's details.
        """
        self._event_bus.publish(
            event_module.Event.now(kind, self._trader_name, payload)
        )
