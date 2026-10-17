# agent_turn_runner.py

## Thinking, since 2026-10-18

`thinking` and `set_thinking` pass straight through to the loop's backend, the same way `use_model` does.

## Side questions, since 2026-10-18

`side_question` makes one `complete` call on a copy of the conversation with no tool definitions, so the model cannot start a tool round and nothing is appended to the real conversation. The text is not streamed to the web page, because a side answer is shown whole when it arrives.

Running it at the same time as a turn is safe: the copy is taken at once, and the backend clients (ollama's AsyncClient, the OpenAI client) accept concurrent requests.
