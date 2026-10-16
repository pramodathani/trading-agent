# event_routes.py

The handler races the next event against the client hanging up. The first version only waited for events, and the live test on 2026-10-16 showed the problem: a client that disconnected was only noticed when the next event was sent, so on a quiet bus its handler and subscription stayed alive forever, and the stuck handler also stopped the server from shutting down gracefully. `test_closed_event_stream_releases_its_subscription` guards against this coming back.
