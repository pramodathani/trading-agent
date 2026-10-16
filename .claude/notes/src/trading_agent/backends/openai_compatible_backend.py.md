# openai_compatible_backend.py

Uses the `openai` package (3.31.0) and Chat Completions, which OpenAI and almost every local server (vLLM, LM Studio, llama.cpp) speak. It is not in the default `backend_order` because the user has no OpenAI key yet; adding one means setting `TRADING_AGENT_OPENAI_API_KEY` in `.env` and adding a `[backends.openai]` table with `kind = "openai_compatible"`, `base_url = "https://api.openai.com/v1"` and a model name.

Streamed tool calls arrive in pieces keyed by their index in the reply: the first piece carries the id and name, later pieces carry fragments of the arguments' JSON text. The pieces are joined per index and parsed once the stream ends. Arguments that are not valid JSON are kept as text under `unparseable_arguments`, a key no tool accepts, so the registry refuses the call and the model sees exactly what it wrote; the turn is not crashed.

`max_retries=0` because the model router does the retrying, with its own waiting periods, across backends. `stream_options={'include_usage': True}` makes the server send token counts in the final chunk.

Local servers that need no key are given a placeholder, because the client refuses an empty key.
