# openai_compatible_backend.py

Uses the `openai` package (3.31.0) and Chat Completions, which OpenAI and almost every local server (vLLM, LM Studio, llama.cpp) speak. It is not in the default `backend_order` because the user has no OpenAI key yet; adding one means setting `TRADING_AGENT_OPENAI_API_KEY` in `.env` and adding a `[backends.openai]` table with `kind = "openai_compatible"`, `base_url = "https://api.openai.com/v1"` and a model name.

Streamed tool calls arrive in pieces keyed by their index in the reply: the first piece carries the id and name, later pieces carry fragments of the arguments' JSON text. The pieces are joined per index and parsed once the stream ends. Arguments that are not valid JSON are kept as text under `unparseable_arguments`, a key no tool accepts, so the registry refuses the call and the model sees exactly what it wrote; the turn is not crashed.

`max_retries=0` because the model router does the retrying, with its own waiting periods, across backends. `stream_options={'include_usage': True}` makes the server send token counts in the final chunk.

Local servers that need no key are given a placeholder, because the client refuses an empty key.

## Pictures, since 2026-10-17

A user message with pictures is sent with `content` as a list: one `text` part, then one `image_url` part per picture as a `data:` address. This is the Chat Completions format for vision input, which OpenAI and llama.cpp's server both accept. A message without pictures still sends `content` as a plain string, as before.

Tool results still cannot carry pictures in Chat Completions, so a tool's screenshot still gets the "cannot be shown to this model" note.

## Pictures from tools

Chat Completions allows only text in a `tool` message. Before attachments part 2 a tool's picture was dropped with a note, so Qwen could not use `browser_screenshot` or `view_image` even though it can see pictures. Now the tool message says the picture is in the next user message, and `_add_tool_pictures` adds one user message after each run of tool results holding every picture from that run, named in order. Grouping them keeps the rule that all tool results follow their assistant message directly, which servers enforce; a user message between two tool results would be refused. Checked live on 17 October 2026: qwen3.8:27b on llama.cpp read the word and number in a test picture through `view_image`.
