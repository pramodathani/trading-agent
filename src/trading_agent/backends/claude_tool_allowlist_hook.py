"""A PreToolUse hook that lets Claude Code run only trading-agent's own tools.

Claude Code's built-in tools are already switched off with `tools=[]`. This hook is a second lock: if a later Claude Code version, a plugin or a setting ever offered another tool, the call would still be refused. Claude Code's own Bash in particular would bypass the bwrap sandbox and the risk engine.

Typical usage example:

  hook = ClaudeToolAllowlistHook(['mcp__trading_agent__get_time'])
  hooks = {'PreToolUse': [claude_agent_sdk.HookMatcher(hooks=[hook])]}
"""

from collections.abc import Sequence
from typing import Any


class ClaudeToolAllowlistHook:
    """Refuses every tool call whose name is not on the allow list."""

    def __init__(self, allowed_tool_names: Sequence[str]):
        """Creates the hook.

        Args:
            allowed_tool_names (Sequence[str]): The tool names Claude may call, as Claude Code names them.
        """
        self._allowed_tool_names = set(allowed_tool_names)

    async def __call__(
        self,
        hook_input: dict[str, Any],
        tool_use_id: str | None,
        context: Any,
    ) -> dict[str, Any]:
        """Decides whether one tool call may run.

        Args:
            hook_input (dict[str, Any]): The hook's input from Claude Code, including tool_name.
            tool_use_id (str | None): The call's identifier, unused.
            context (Any): The hook context, unused.

        Returns:
            dict[str, Any]: An empty dict to allow the call, or a PreToolUse deny decision.
        """
        del tool_use_id, context
        tool_name = hook_input.get('tool_name', '')
        if tool_name in self._allowed_tool_names:
            return {}
        return {
            'hookSpecificOutput': {
                'hookEventName': 'PreToolUse',
                'permissionDecision': 'deny',
                'permissionDecisionReason': f"{tool_name} is not one of trading-agent's tools.",
            },
        }
