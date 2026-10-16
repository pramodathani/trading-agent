# desk_runtime.py

A desk handles one trigger at a time, so it can never run two turns that trade at once. Separate desks each have their own runtime and run side by side, so a slow positional decision never delays the scalper.

A turn that raises is caught at this level and published as an `error` event, and the loop carries on. This is the isolation point for a desk: one bad turn, for example a model that returns garbage, must not stop the desk for the rest of the day. The exception is logged with its traceback for the logs page.

`submit` refuses a trigger addressed to another desk. Routing mistakes would otherwise make one persona act on another persona's instructions.

`turn_finished` is published in a `finally` block so that listeners such as the web interface always see a turn end, whether it succeeded or failed.

The desk closes its turn runner in the same `finally` block that marks it stopped, so a cancelled desk always releases its Claude Code process.
