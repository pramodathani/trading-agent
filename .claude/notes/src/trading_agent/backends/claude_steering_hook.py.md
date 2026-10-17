# claude_steering_hook.py

Claude Code runs the whole turn inside its own process, so trading-agent cannot add a message between its steps the way the agent loop does. Claude Code's hooks are the one place it asks trading-agent something during a turn. After every tool call it runs the PostToolUse hooks, and a hook may return `additionalContext`, which Claude reads before its next step. The SDK documents this field for PostToolUse in claude-agent-sdk 0.2.168.

The hook takes the messages out of the inbox, so each is given once.
