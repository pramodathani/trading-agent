# telegram_channel.py

The channel is a background worker of the gateway, like the market watcher. It has two loops in one task group: the message loop (Telegram to the desks) and the event loop (the desks to Telegram).

## Strangers

A chat that is not paired gets a pairing code and nothing else, and every message from it is published as a `channel` event, so it appears on the Activity page and in the journal; the plan asks for strangers' messages to be logged. Only the first 200 characters are kept.

## Answers go back to the chat that asked

A message from a paired chat becomes a user-message trigger on the chat's desk. The channel remembers which chat sent which trigger, and when the desk's text (or error) for that trigger arrives, it is sent to that chat only. A message typed on the web page is therefore not echoed to Telegram, and a Telegram conversation is not broadcast to other chats.

## Steering from the phone

If the desk is working, the desk's runtime turns the message into steering. When the steering event says it was delivered, the channel tells the chat and adds the chat to the running turn's reply list, so the answer that took the message into account reaches the phone. A message that was not delivered in time becomes its own turn, and its answer comes back as usual.

## Failures

Telegram being unreachable never stops the gateway: connecting and polling retry after 5 seconds, doubling up to two minutes, and the Channels page shows the error. A failed send is logged and skipped. A failure while forwarding one event is logged and the loop carries on, because one malformed event must not silence every later notification.

## Approving from the web page

`approve` pairs the chat and tells it at once. `trading-agent pairing approve` cannot message the chat, because it runs in another process; the chat is simply obeyed from its next message, as docs/telegram_setup.md says.
