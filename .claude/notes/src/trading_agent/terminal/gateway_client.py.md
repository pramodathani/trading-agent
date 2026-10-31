# gateway_client.py

One method per route of `frontend/src/api/apiClient.ts`, plus `trader_commands` and `health`. Errors carry FastAPI's `detail`, joined when it is a list of validation errors, because that is the text a person can act on. A connection failure becomes `GatewayError` with status 0 and the commands that start the gateway, so every caller can show one helpful message.

Tests pass an `httpx.ASGITransport` so the client calls a real `GatewayApplication` in the same process without a port.

## Trader records

`trader_records`, `create_trader`, `retire_trader` and `restore_trader` call the roster routes, for `trading-agent traders`.
