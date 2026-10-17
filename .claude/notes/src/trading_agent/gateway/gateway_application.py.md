# gateway_application.py

The desks run inside the web server's lifespan: their loops start when the server starts and are cancelled when it stops. This makes the gateway a single process that owns every desk, like OpenClaw's and Hermes's gateways, so there is no second process to keep in step.

Routes are built by small classes, one per group, which receive only what they need. That keeps each route group testable on its own with FastAPI's test client.

Since milestone 8 the gateway also runs background workers, such as the trade journal, beside the desks, and cancels them at shutdown. The live event stream passes through the secret redactor.

## Webhooks (milestone 15)

The gateway includes the webhook route, which carries no gateway-token dependency because it checks its own token.

## Route groups (milestone 17)

The application builds every API route group and passes them in as `route_groups`. When none are given, the gateway offers only the basic desk routes, which keeps the older tests and small test setups working without the full set of parts.

## The web page (milestone 18)

When `frontend_directory` is given, the frontend route is added after every other route, because it matches every address.
