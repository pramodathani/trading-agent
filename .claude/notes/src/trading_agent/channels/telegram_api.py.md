# telegram_api.py

The only file that imports python-telegram-bot (22.8). Keeping the library behind this small class means the channel's logic is tested with a stand-in and never needs the internet, and a future change of library touches one file.

## Long polling rather than a webhook

Telegram can either push messages to a public address (a webhook) or let the bot ask for them. Asking needs no open port, no public address and no TLS certificate, which suits a gateway bound to 127.0.0.1. Each request waits up to `poll_seconds` (30 by default) and returns at once when a message arrives, so replies are immediate. The read timeout is ten seconds longer than the poll, so a quiet poll is not mistaken for a network failure.

`get_updates` is given an offset one past the last update, which tells Telegram those updates are handled; a restart therefore does not replay old messages.

Only text messages are handled; photos and stickers are skipped for now.

## Sending

Telegram refuses messages over 4096 characters, so long answers are split at line breaks into parts of at most 4000. Messages are sent as plain text, with no Markdown, because a desk's answer can contain characters that Telegram's Markdown would misread and refuse.

The bot's library is used directly (`telegram.Bot`) rather than its `Application` framework, because the gateway already has its own event loop and background workers; a plain loop of `get_updates` is easier to follow and to stop.

## Photos and files, since 2026-10-17

`messages` now returns messages that carry a photo or a file, with the caption as the text, and still skips stickers, voice notes and the like. Files are not downloaded here: `IncomingFile` only holds Telegram's id, and `download` fetches the bytes later, so the channel can refuse files from strangers, or files over 20 MB, without fetching them.

Telegram sends a photo in several sizes, smallest first; the largest is taken. Photos have no name, so one is made from the message id. Telegram compresses photos sent as "Photo"; a file sent as "File" arrives as it was.

Telegram's Bot API lets a bot download files of up to 20 MB, which is why the store's limit is the same.

## send_photo

Telegram refuses a photo over 10 MB, or one whose width and height add up to more than 10,000 pixels or whose sides differ by more than 20 times, with a `BadRequest`. A tall table rendered by a desk can hit the proportion rule, so on `BadRequest` the picture is sent again as a document, which has no such limits and still previews in the app. A caption over Telegram's 1,024 characters is sent as a separate message after the picture rather than cut.

## set_commands, since 2026-10-18

`set_commands` wraps python-telegram-bot's `set_my_commands`. It sets the menu for all private chats in the default scope, which is the only kind of chat the bot is paired with.
