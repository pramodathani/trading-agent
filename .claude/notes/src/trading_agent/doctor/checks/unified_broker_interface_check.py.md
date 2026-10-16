# unified_broker_interface_check.py

UBI's address is read through tradingmachine's own `Configuration` class, from the same `.env` file the trading tools will use, so the doctor checks the real route the agent will take rather than a copy of the address. Any HTTP answer, even 404, proves UBI is running; on 2026-10-16 it answered 404 at its root address. The check deliberately does not connect a session, because `UnifiedBrokerInterface` reads credentials from MongoDB and `disconnect()` would log every client out.
