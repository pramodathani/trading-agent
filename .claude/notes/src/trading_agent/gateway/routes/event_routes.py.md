# event_routes.py

The handler races the next event against the client hanging up. The first version only waited for events, and the live test on 2026-10-16 showed the problem: a client that disconnected was only noticed when the next event was sent, so on a quiet bus its handler and subscription stayed alive forever, and the stuck handler also stopped the server from shutting down gracefully. `test_closed_event_stream_releases_its_subscription` guards against this coming back.

## Trader filter (milestone 17)

A client can add `trader=<name>` to receive one trader's events only. Events that belong to no trader, such as account status and the kill switch, are always sent, because every trader's page needs to know about them. The filter runs in the handler rather than in the bus, so the bus stays simple and every subscriber still costs one queue. The live test on 2026-10-17 sent `/status` to the scalper and the intraday trader with the stream filtered to intraday, and only intraday's four events arrived.
