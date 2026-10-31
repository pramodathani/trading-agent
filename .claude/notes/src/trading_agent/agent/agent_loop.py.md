# agent_loop.py

This is the loop Pi is built around: ask the model, run every tool it asks for, append the results, ask again, and stop when it answers without a tool call.

Several tool calls in one reply run at the same time with `asyncio.gather`, and all their results are appended together, in the order the calls were made. Every step is published on the event bus, so the web interface and journal can show the turn as it happens.

The round limit (20 by default, from `[agent]` in `trading_agent.toml`) ends a turn whose model never stops calling tools. A backend that cannot be reached raises `BackendUnavailableError`, which the trader runtime turns into an error event today and the model router will catch in milestone 4.

The first live run on 2026-10-16 with Gemma 4 31b called `get_time` unprompted, answered in 6.9 seconds over two rounds, and remembered the question in the following turn.

## Compression (milestone 12)

`run_turn` checks the compressor before the turn and, at 70%, runs `_flush_and_compress`: a flush turn through `_run_rounds`, then compression of everything. `_run_rounds` is the old body of `run_turn`; between rounds (never before round 1, whose count is from the previous turn and already checked) it compresses at 85% while keeping the current turn's messages, and records the reported tokens after appending each reply, so the reply is not counted twice. A server that reports no prompt tokens leaves the last measurement in place, so the estimate keeps growing instead of resetting to zero. `compact` serves `/compact`.

## Steering and /stop (milestone 18)

After the results of a tool round are added, the loop asks the steering inbox for waiting messages and adds them as a user message, so the next model call sees them.

When /stop cancels a turn during a tool round, the conversation would end with an assistant message asking for tools that have no results. OpenAI-compatible servers refuse such a conversation on the next call. The loop therefore answers each unanswered call with an error result saying the user stopped the turn. Results are only added after every call of a round finishes, so a round is either fully answered or not at all.

## Pictures, since 2026-10-17

`_run_rounds` puts the trigger's pictures on the turn's user message, prepared by `ImagePreparer`. A picture whose file cannot be read is left out rather than failing the turn. Only the first user message of a turn carries pictures; steering messages are text, and messages with attachments never steer.

Four pictures are kept (`_PICTURES_KEPT`) before every model call, including between tool rounds of one turn. Four covers a follow-up question about a chart sent in the previous turn, plus a few screenshots, while capping pictures at about 6,000 tokens. Claude's history is held by Claude Code, not by this loop, so the trimming does not apply to it; Claude Code compacts its own history.
