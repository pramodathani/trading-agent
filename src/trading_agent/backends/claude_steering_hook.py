"""A PostToolUse hook that hands the user's mid-turn messages to Claude.

After every tool call, Claude Code asks this hook whether to add anything to what Claude reads next. When the desk's steering inbox holds messages, the hook returns them as additional context, so Claude sees them before its next step, exactly as the agent loop adds them for the local models.

Typical usage example:

  hook = ClaudeSteeringHook(inbox)
  hooks = {'PostToolUse': [claude_agent_sdk.HookMatcher(hooks=[hook])]}
"""

from typing import Any

from trading_agent.runtime import steering_inbox as steering_inbox_module


class ClaudeSteeringHook:
    """Adds waiting user messages to Claude's context after each tool call."""

    def __init__(self, inbox: steering_inbox_module.SteeringInbox):
        """Creates the hook.

        Args:
            inbox (steering_inbox_module.SteeringInbox): The desk's steering inbox.
        """
        self._inbox = inbox

    async def __call__(
        self,
        hook_input: dict[str, Any],
        tool_use_id: str | None,
        context: Any,
    ) -> dict[str, Any]:
        """Returns the waiting messages, if any.

        Args:
            hook_input (dict[str, Any]): The hook's input from Claude Code, unused.
            tool_use_id (str | None): The call's identifier, unused.
            context (Any): The hook context, unused.

        Returns:
            dict[str, Any]: An empty dict when nothing is waiting, or a PostToolUse output with the messages as additional context.
        """
        del hook_input, tool_use_id, context
        text = self._inbox.take_text()
        if text is None:
            return {}
        return {
            'hookSpecificOutput': {
                'hookEventName': 'PostToolUse',
                'additionalContext': text,
            },
        }
