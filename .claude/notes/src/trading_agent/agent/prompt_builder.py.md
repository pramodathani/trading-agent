# prompt_builder.py

The prompt is rebuilt before every turn, so an edit to a workspace file reaches the trader on its next turn without a restart. It holds only slow-changing text: the trader's name, the mode and the files. The time and the trigger go in the user message (see `trader_runtime.py`), because anything that changes every turn in the system prompt would make the model's prompt cache miss every time.

The order is Agents.md, Persona.md, User.md, TradingRules.md, Memory.md: general rules first, then the trader's own style, then the user and the hard limits, then lessons. The caps (20,000 characters per file, 60,000 in total) come from OpenClaw's bootstrap-file limits, and keep a runaway Memory.md from filling Gemma's 32,768-token context.

The fingerprint is the first 16 hex digits of the text's SHA-256. The Claude runner compares it with the fingerprint its Claude Code process was started with, and restarts the process (resuming the same session) when they differ, because Claude Code takes its system prompt only at start.

## How your memory works (milestone 11)

A fixed section after the header explains sessions, the rollover, `add_note`, `search_sessions` and checkpoints. It lives in code rather than in `Agents.md` because it describes how the program works, which the user should not have to keep in step with the code. The header line now mentions it. Changing it changed every trader's prompt fingerprint once, so Claude received the new instructions inside its next message.

## Skills index (milestone 13)

With a skill library, the index of usable skills comes last in the prompt, after Memory.md. It changes only when a skill is imported, written, patched or archived, so the prompt cache keeps working between those events.

## MCP tool names (milestone 13)

With MCP servers configured, a last section lists each server's tool names (or its state when not ready) and how to use `tool_search` and `call_mcp_tool`. It changes when a server connects or fails, which changes the prompt's fingerprint; Claude then receives the updated instructions inside its next message.

## Subagents (milestone 14)

With a subagent library, the Subagents section (names, descriptions and how delegate_task works) comes after the skills index.

## Other traders (milestone 16)

The header names the other enabled traders and says the risk engine gives each instrument to one trader at a time, so a trader does not plan trades in a stock another trader holds.
