"""Runs one tool call the same way for every backend.

Whether the call comes from the agent loop (Gemma, Qwen, OpenAI) or from Claude Code, it is published, checked by the loop guard and the permission gate, run through the registry, and its result published. Keeping that in one place means every backend gets the same protections.

Typical usage example:

  executor = ToolCallExecutor('main', registry, event_bus, loop_guard)
  executor.start_turn()
  result = await executor.execute(trigger, call)
"""

from trading_agent.agent import loop_guard as loop_guard_module
from trading_agent.agent import messages
from trading_agent.requests import permission_gate as permission_gate_module
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.tools import tool as tool_module
from trading_agent.tools import tool_registry as tool_registry_module


class ToolCallExecutor:
    """Runs a desk's tool calls through the loop guard and the registry.

    Attributes:
        tool_registry: The desk's tools.
    """

    def __init__(
        self,
        desk_name: str,
        tool_registry: tool_registry_module.ToolRegistry,
        event_bus: event_bus_module.EventBus,
        loop_guard: loop_guard_module.LoopGuard,
        permission_gate: permission_gate_module.PermissionGate | None = None,
    ):
        """Creates the executor.

        Args:
            desk_name (str): The desk the calls belong to, used to tag events.
            tool_registry (tool_registry_module.ToolRegistry): The desk's tools.
            event_bus (event_bus_module.EventBus): Where calls and results are published.
            loop_guard (loop_guard_module.LoopGuard): The guard against repeated identical calls.
            permission_gate (permission_gate_module.PermissionGate | None): Holds calls that need the user's permission, or None when none do.
        """
        self._desk_name = desk_name
        self._permission_gate = permission_gate
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
        elif gate is not None and gate.needs_permission(self._desk_name, call.name):
            result = gate.hold(self._desk_name, call)
        else:
            result = await self.tool_registry.run(call)
        payload = {
            'trigger_id': trigger.trigger_id,
            'call_id': call.call_id,
            'name': call.name,
            'is_error': result.is_error,
            'text': result.text,
        }
        if result.picture_desk_path is not None:
            payload['picture_path'] = result.picture_desk_path
        self._publish(event_module.EventKind.TOOL_RESULT, payload)
        return result

    def _publish(self, kind: event_module.EventKind, payload: dict) -> None:
        """Publishes an event from this desk.

        Args:
            kind (event_module.EventKind): What happened.
            payload (dict): The event's details.
        """
        self._event_bus.publish(
            event_module.Event.now(kind, self._desk_name, payload)
        )
