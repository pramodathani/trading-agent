"""A PreCompact hook that records each time Claude Code compacts a trader's session.

trading-agent normally compacts Claude's session itself, between turns at 70% of the window, after a memory-flush turn. Claude Code's own automatic compaction is the safety net for one very long turn. When it fires, this hook publishes the event and tells the turn runner, so the runner can send the instruction files again on the next turn, because a compacted session may have lost updated instructions that were delivered inside earlier messages.

Typical usage example:

  hook = ClaudePreCompactHook('main', 'claude', event_bus, runner.note_compaction)
  hooks = {'PreCompact': [claude_agent_sdk.HookMatcher(hooks=[hook])]}
"""

from collections.abc import Callable
from typing import Any

from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module


class ClaudePreCompactHook:
    """Tells the runner about every compaction, and publishes the automatic ones.

    A manual compaction is always one the turn runner started with /compact, and the runner publishes a fuller event for it itself, so the hook does not publish a second one.
    """

    def __init__(
        self,
        trader_name: str,
        backend_name: str,
        event_bus: event_bus_module.EventBus,
        on_compaction: Callable[[], None],
    ):
        """Creates the hook.

        Args:
            trader_name (str): The trader, used to tag the event.
            backend_name (str): The backend's name in trading_agent.toml.
            event_bus (event_bus_module.EventBus): Where the event is published.
            on_compaction (Callable[[], None]): Called once per compaction, so the runner can resend its instructions.
        """
        self._trader_name = trader_name
        self._backend_name = backend_name
        self._event_bus = event_bus
        self._on_compaction = on_compaction

    async def __call__(
        self,
        hook_input: dict[str, Any],
        tool_use_id: str | None,
        context: Any,
    ) -> dict[str, Any]:
        """Notes the compaction, publishes it if it is automatic, and lets it go ahead.

        Args:
            hook_input (dict[str, Any]): The hook's input from Claude Code, including trigger ("auto" or "manual").
            tool_use_id (str | None): Unused; compaction is not a tool call.
            context (Any): The hook context, unused.

        Returns:
            dict[str, Any]: An empty dict, which lets the compaction proceed.
        """
        del tool_use_id, context
        self._on_compaction()
        trigger = hook_input.get('trigger', 'auto')
        if trigger == 'manual':
            return {}
        self._event_bus.publish(
            event_module.Event.now(
                event_module.EventKind.CONTEXT_COMPRESSED,
                self._trader_name,
                {
                    'backend': self._backend_name,
                    'reason': f'claude_code_{trigger}',
                },
            )
        )
        return {}
