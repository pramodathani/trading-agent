# telegram_channel.py

The channel is a background worker of the gateway, like the market watcher. It has two loops in one task group: the message loop (Telegram to the traders) and the event loop (the traders to Telegram).

## Strangers

A chat that is not paired gets a pairing code and nothing else, and every message from it is published as a `channel` event, so it appears on the Activity page and in the journal; the plan asks for strangers' messages to be logged. Only the first 200 characters are kept.

## Answers go back to the chat that asked

A message from a paired chat becomes a user-message trigger on the chat's trader. The channel remembers which chat sent which trigger, and when the trader's text (or error) for that trigger arrives, it is sent to that chat only. A message typed on the web page is therefore not echoed to Telegram, and a Telegram conversation is not broadcast to other chats.

## Steering from the phone

If the trader is working, the trader's runtime turns the message into steering. When the steering event says it was delivered, the channel tells the chat and adds the chat to the running turn's reply list, so the answer that took the message into account reaches the phone. A message that was not delivered in time becomes its own turn, and its answer comes back as usual.

## Failures

Telegram being unreachable never stops the gateway: connecting and polling retry after 5 seconds, doubling up to two minutes, and the Channels page shows the error. A failed send is logged and skipped. A failure while forwarding one event is logged and the loop carries on, because one malformed event must not silence every later notification.

## Approving from the web page

`approve` pairs the chat and tells it at once. `trading-agent pairing approve` cannot message the chat, because it runs in another process; the chat is simply obeyed from its next message, as docs/telegram_setup.md says.

## Photos and files, since 2026-10-17

A paired chat's photo or file is downloaded and stored as an upload, and sent to the trader with the caption as the message text. The pairing check comes first, so a stranger's file is never downloaded; a test checks that. A file Telegram reports as larger than 20 MB is refused before downloading, and any refusal is told to the chat in the store's words.

A message with a file is never treated as a command, even when its caption starts with a slash, because the file is meant for a trader. Storing runs in a worker thread, as on the web, because reading a PDF can take a second.

## Pictures from send_image

A `message` event with `attachments` is a picture from `send_image`, and is sent with `send_photo` instead of as text. The event carries no `trigger_id`, because tools do not know their trigger, so the channel remembers each trader's running trigger from `turn_started` and `turn_finished`. A trader runs one turn at a time, so this identifies the turn exactly. When that turn came from a Telegram chat, the picture goes to that chat whatever the notification settings, because the user asked for it; otherwise it is pushed to every paired chat only when `messages` notifications are on, with the formatter's "Picture from <trader>:" caption. The caption goes on the first picture only.

The picture is read from the absolute `path` in the attachment dictionary rather than looked up in the store, so the channel works when it was built without a store. The path comes from our own tool, not from a model or a user.

## Command menu, since 2026-10-18

After each successful connect, `_register_menu` sends `TelegramCommands.menu()` to Telegram with `setMyCommands`. A refusal is logged and ignored, because the bot works without a menu and a failed menu must not keep the channel from starting.

## Introducing traders made by /create

After answering a code-only command, the channel takes the introductions `/create` queued and submits each as a user message from the asking chat, so the new trader's first reply comes back to that chat.
