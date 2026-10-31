# jev_decision_tool.py

The jev_decision tool, given only to traders whose trader.toml sets `jev_signals` (see trader_builder.py).

It takes no arguments. The jev-scalper's strategy is about NIFTY alone, and letting the model pass an instrument or a description would let it shape what Jev sees. If another Jev strategy needs other instruments later, an instrument argument can be added then.

A failure is returned as an error whose text says to treat the moment as hold. That puts the safe reading in front of whichever model is running, including the smaller local ones.

The tool's timeout is 60 seconds, the same as the broker tools, because most of its time is the UBI read rather than Jev.
