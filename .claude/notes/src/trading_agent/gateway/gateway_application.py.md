# gateway_application.py

The desks run inside the web server's lifespan: their loops start when the server starts and are cancelled when it stops. This makes the gateway a single process that owns every desk, like OpenClaw's and Hermes's gateways, so there is no second process to keep in step.

Routes are built by small classes, one per group, which receive only what they need. That keeps each route group testable on its own with FastAPI's test client.

Since milestone 8 the gateway also runs background workers, such as the trade journal, beside the desks, and cancels them at shutdown. The live event stream passes through the secret redactor.
