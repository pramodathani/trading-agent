# claude_code_backend_check.py

An `ANTHROPIC_API_KEY` in the environment is a failure, not a warning. Claude Code's authentication docs say that in non-interactive mode the key "is always used when present", which would silently bill the API instead of the user's Max subscription.

The check runs the Claude Code program the Agent SDK will actually use. The SDK prefers its own bundled copy (`claude_agent_sdk/_bundled/claude`) over the `claude` on PATH, and the two can differ in version after an upgrade of one but not the other. On 2026-10-16 both were 2.1.301.
