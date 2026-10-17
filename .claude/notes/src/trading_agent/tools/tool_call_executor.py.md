# tool_call_executor.py

Moved out of `agent_loop.py` in milestone 3, when the Claude Code backend needed exactly the same steps: publish the call, ask the loop guard, run it through the registry, publish the result. With one executor, a tool call gets the same protections whichever model made it, and a later protection (for example the risk engine in milestone 9) is added in one place.

The loop guard is reset by `start_turn`, which both the agent loop and the Claude runner call at the start of every turn.

## Pictures in tool cards

When a result has `picture_desk_path`, the `tool_result` event gets a `picture_path` key. The key is left out otherwise rather than set to null, so the many existing journal lines and the tests that compare whole payloads are unchanged.
