
## Which client answered

Since 2026-10-18 a client may name itself with the header `X-Trading-Agent-Client`. Only `terminal` is accepted besides the default `web`; any other value is recorded as `web`, so a stray header cannot write arbitrary text into the request store. The terminal program sends the header on every request through `GatewayClient`, so its answers show "via terminal" in the transcript and "in the terminal" on Telegram. A header was chosen over a body field because all four response routes needed it and the dismiss route has no body.
