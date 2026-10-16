# access_guard.py

The token comparison uses `hmac.compare_digest`, which takes the same time whether the first character or the last one differs, so the token cannot be guessed one character at a time by timing the answers.

An empty token is refused when the guard is built, because comparing against an empty string would let any request without a token in.

WebSockets carry the token as a query parameter because browsers cannot set an `Authorization` header on a WebSocket. Query parameters appear in uvicorn's log lines, which is why `token_redacting_filter.py` exists.
