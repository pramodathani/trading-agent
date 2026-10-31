# tool_registry.py

The registry is the single point where a model's request meets real code, so every protection lives here and every tool gets it for free:

- an unknown tool name returns the list of real tools, so the model can correct itself;
- invalid arguments are refused before the tool runs;
- a time limit (`tool_timeout_seconds`, 60 by default) stops a hung tool;
- an exception becomes an error result and is logged with its traceback, so a broken tool cannot end the turn or crash the trader;
- output longer than 20,000 characters is cut with a note, so one tool cannot fill Gemma's 32,768-token context.

`run` never raises, which keeps the agent loop simple.

Since milestone 6 a tool may set its own `timeout_seconds`, which the registry uses instead of the default; `bash_run` does so because a command may legitimately run for two minutes. The registry also closes every tool when the trader stops.
