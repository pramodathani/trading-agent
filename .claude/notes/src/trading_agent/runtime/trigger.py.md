# trigger.py

A trigger is one reason to wake a desk: a user message, a cron job, a heartbeat, a market-watcher event, a webhook, a rollover, a compression flush or a subagent task.

## Attachments, since 2026-10-17

`attachments` holds the pictures and documents a user message carries. It defaults to an empty tuple, so every other kind of trigger, and every existing caller of `Trigger.now`, is unchanged.

`to_json_dictionary` writes `attachments` only when there are some, so the events and journals of ordinary turns look exactly as before. The chat page reads the list from the `trigger_received` event to redraw the pictures after a reload.

`images` is a property rather than a stored field because it is a cheap filter of `attachments` and would otherwise have to be kept in step with it.
