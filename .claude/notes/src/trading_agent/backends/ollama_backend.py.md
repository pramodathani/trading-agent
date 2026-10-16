# ollama_backend.py

The backend uses Ollama's own `/api/chat` through the `ollama` package (0.6.3) rather than Ollama's OpenAI-compatible endpoint, because only `/api/chat` accepts `num_ctx` and `think` per request. Without `num_ctx` Ollama uses its small default context and silently drops the start of a long conversation.

A probe on 2026-10-16 showed how Gemma 4 31b streams: the tool call arrives in a chunk before the final one (chunk 81 of 82), with its arguments already a dictionary and no call identifier, and the final chunk carries `prompt_eval_count` and `eval_count`. The code therefore collects tool calls from every chunk and reads the token counts from the chunk marked `done`.

The model's thinking text is not sent back in later requests; Ollama does not need it, and leaving it out saves context.
