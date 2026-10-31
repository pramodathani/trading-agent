# gateway_application.py

The traders run inside the web server's lifespan: their loops start when the server starts and are cancelled when it stops. This makes the gateway a single process that owns every trader, like OpenClaw's and Hermes's gateways, so there is no second process to keep in step.

Routes are built by small classes, one per group, which receive only what they need. That keeps each route group testable on its own with FastAPI's test client.

Since milestone 8 the gateway also runs background workers, such as the trade journal, beside the traders, and cancels them at shutdown. The live event stream passes through the secret redactor.

## Webhooks (milestone 15)

The gateway includes the webhook route, which carries no gateway-token dependency because it checks its own token.

## Route groups (milestone 17)

The application builds every API route group and passes them in as `route_groups`. When none are given, the gateway offers only the basic trader routes, which keeps the older tests and small test setups working without the full set of parts.

## The web page (milestone 18)

When `frontend_directory` is given, the frontend route is added after every other route, because it matches every address.

## Cross-origin requests from the Android app

The Android app bundles its own copy of the web page, which Capacitor serves from `https://localhost` on the phone. Its calls to the gateway are therefore cross-origin, and the WebView blocks them unless the gateway answers with CORS headers. `allowed_origins` (from `[gateway] allowed_origins`) lists the origins that may call; an empty list adds no middleware at all, which is the old behaviour.

Only the `Authorization` and `Content-Type` headers are allowed and credentials (cookies) are not, because the gateway authenticates with a bearer token and never uses cookies. A malicious page elsewhere cannot use this to reach the API: it would still need the token, and its origin is not on the list. The WebSocket is not covered by CORS; it checks its `?token=` itself.

## Trader runner

Given a trader runner (the trader registry), the lifespan calls its `start()` and `stop()` instead of starting one task per trader, so a trader created while the gateway runs gets its loop. Tests that pass only a dictionary of traders still get one task each.
