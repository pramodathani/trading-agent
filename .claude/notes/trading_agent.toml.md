# trading_agent.toml

This file holds everything that is not secret, so it can be committed. Secrets live in `.env`.

- `mode = "dry_run"` stays until milestone 21, when the user's decision to trade live from day one is applied at the first real start. Until then every order the build's tests send goes to UBI as a dry run.
- The gateway listens on 127.0.0.1:8120. Ports 8100 and 8110 were already taken on this machine on 2026-10-16, and binding to 127.0.0.1 keeps it off the network.
- `gemma` points at the local Ollama server. Its `context_window` is 32,768, not the model's maximum of 262,144, because the 31b model already takes about 20 GB of the RTX 4090's 24 GB, which leaves little room for a long context.
- `qwen` points at the llama.cpp server that the Hermes install already runs on port 18434. That server asks for an API key, which is added in milestone 4.
- `claude` has no address because it runs through Claude Code, not over HTTP. The model name `opus` is Claude Code's alias for the current Opus model.
- The single desk `main` is a stand-in until milestone 16 introduces the intraday, scalper and positional desks.

Since milestone 3 the `main` desk's `backend_order` is Claude first, then Gemma.
