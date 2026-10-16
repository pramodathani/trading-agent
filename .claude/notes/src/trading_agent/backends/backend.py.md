# backend.py

A backend answers one model call; the agent loop owns the loop. That split works for Ollama and for OpenAI-compatible servers. Claude Code runs its own loop internally, so the Claude backend (milestone 3) will be a turn runner of its own rather than a subclass of `ModelBackend`.

`BackendUnavailableError` marks the failures where trying another backend makes sense: the server is down, unreachable or refused the request.
