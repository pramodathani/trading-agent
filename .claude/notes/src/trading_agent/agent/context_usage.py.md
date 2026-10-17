# context_usage.py

Claude's snapshot is taken by `ClaudeCodeTurnRunner` right after each turn and after each compaction, with `ClaudeSDKClient.get_context_usage()`, and kept until the next one. The gateway route only reads the kept snapshot, so a request never talks to the Claude Code process while a turn may be running. After a restart, Claude has no snapshot until its next turn.

The agent runners (Ollama, OpenAI) estimate on request. A first version counted the tool definitions at three characters per token and took the messages as the remainder of the measured total; on Qwen that gave 15.6k tokens of tools against a measured total of 10.5k, so the messages came out as 0. The rough counts of system prompt, tools and messages are now scaled together to the total the model reported, which keeps their proportions and makes them add up.
