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

## Session keeper (milestone 11)

When the desk has a session keeper, `run` calls `keeper.start()` before the first trigger, so `/status` shows the resumed session straight away, and `_answer` calls `keeper.prepare(trigger)` before each model turn. `prepare` runs before `_with_context`, so the India-time line stays the first line of the message even when a summary is put in front of the trigger. Commands and paused desks skip `prepare`, so `/status` never triggers a rollover.

## /<skill-name> (milestone 13)

A slash message is first offered to `skill_request`; if it names a usable skill, the trigger's text is replaced and the message goes down the normal model path, paused check and session keeper included. Otherwise it is handled as a command, as before.

## NOTHING_TO_DO and /rollover (milestone 15)

Every `text` event now carries `silent`: true when a heartbeat or scheduled job was answered with exactly NOTHING_TO_DO. The journal still records it; the web interface and Telegram will skip it, so an all-quiet heartbeat sends no message. `roll_over` serves `/rollover`.

## usage_tracker (milestone 15)

The desk holds the gateway's usage tracker so /usage can read it.

## Market line (milestone 16)

With a `MarketStatus`, the context line ends with " · market: ..." (see scheduling/market_status.py.md).

## Steering and /stop (milestone 18)

`submit` handles two cases before queueing:

1. `/stop` is answered at once and never queued, because a stop that waited for the running turn to end would be useless. If a model turn is running, it is cancelled. The /stop gets its own small turn in the events (started, text, finished), so the web page shows it like any other message.
2. A user message, not a command, that arrives during a model turn goes to the steering inbox, with `steering_into` in its trigger_received event.

The model turn runs as its own asyncio task so it can be cancelled without cancelling the desk's loop. A `_stop_requested` flag tells a cancellation from /stop apart from the gateway shutting down: only the first is turned into the "Stopped by the user" answer and a `stopped` event; a shutdown's cancellation is passed on.

Stopping does not undo tools that already ran, such as an order already placed; the reply says so.

After every model turn, messages the turn never picked up are queued as their own turns.

## Attachments, since 2026-10-17

`_with_context` adds one note line per attachment after the message text, from `Attachment.describe_for_model`. The notes go into the turn's text, which every backend sends, so a document's location reaches Claude, Ollama and OpenAI the same way; the pictures themselves are added by each backend.

`_can_steer` is False for a message with attachments. Steering hands a running turn text only (for Claude through a hook's `additionalContext`, which cannot carry pictures), so a picture sent mid-turn would be lost. Such a message becomes its own turn instead.
