# desk_runtime.py

A desk handles one trigger at a time, so it can never run two turns that trade at once. Separate desks each have their own runtime and run side by side, so a slow positional decision never delays the scalper.

A turn that raises is caught at this level and published as an `error` event, and the loop carries on. This is the isolation point for a desk: one bad turn, for example a model that returns garbage, must not stop the desk for the rest of the day. The exception is logged with its traceback for the logs page.

`submit` refuses a trigger addressed to another desk. Routing mistakes would otherwise make one persona act on another persona's instructions.

`turn_finished` is published in a `finally` block so that listeners such as the web interface always see a turn end, whether it succeeded or failed.

The desk closes its turn runner in the same `finally` block that marks it stopped, so a cancelled desk always releases its Claude Code process.

## Commands, pause and the context line (milestone 5)

A message that starts with `/` is answered by `SlashCommands`. Every other message is sent to the turn runner with a first line such as `[India time: Friday 2026-10-16 23:50:12 IST · woken by: user_message]`. Those facts change every turn, so they belong in the message rather than in the system prompt, where they would defeat the prompt cache. The time is taken from when the trigger was created, not when the turn starts, so a trigger that waited in the queue still reports when it happened.

While `paused` is true the desk answers ordinary messages with a fixed reply and asks no model.

Since milestone 6 the desk also closes its tool registry when it stops, which ends its bash sandbox.
