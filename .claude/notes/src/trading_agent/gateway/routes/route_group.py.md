# route_group.py

Every API route group repeats the same two things: every route needs the access token, and a trader or other named thing that does not exist must answer 404. The base class does both once. `router()` attaches the guard as a router-wide dependency, so a new route cannot forget it, and `_find()` looks a name up in a mapping and raises the 404.

Each subclass only adds its routes in `_add_routes()`. Inheritance is one level deep on purpose.

The health route, the webhook route and the WebSocket do not use this base: health needs no token, the webhook checks its own token, and a WebSocket carries the token in its query string because browsers cannot set headers on one.
