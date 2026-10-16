# conversation.py

The conversation is append-only on purpose. Claude Opus 5.5 checks that the history sent with each request was not edited after its thinking was produced ("preserved thinking"), and accounts created after 2026-08-31 get an error when it was. Compression in milestone 12 therefore starts a fresh conversation seeded with a summary rather than editing this one.

Until milestones 11 and 12 the conversation lives only in memory and grows without limit; a restart forgets it.
