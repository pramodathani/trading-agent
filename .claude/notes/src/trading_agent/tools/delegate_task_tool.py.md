# delegate_task_tool.py

The trader's way to hand work to subagents: one to four tasks per call, run at the same time. A list rather than one task per call because not every backend runs a model's parallel tool calls at the same time, while a list is parallel everywhere.

Each report is labelled as outside data, because a subagent may have read web pages that try to steer it, and its report could carry that through. The tool description asks the trader to check important claims before acting; in the live test Claude did exactly that. The result is an error only when no task produced a report, so the trader changes course.

Its timeout is the subagent maximum (1,800 s) plus a minute. Claude Code's own limit on one tool call is raised to match (`MCP_TOOL_TIMEOUT`, see claude_code_turn_runner.py).
