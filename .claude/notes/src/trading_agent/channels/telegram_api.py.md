# telegram_api.py

The only file that imports python-telegram-bot (22.8). Keeping the library behind this small class means the channel's logic is tested with a stand-in and never needs the internet, and a future change of library touches one file.

## Long polling rather than a webhook

Telegram can either push messages to a public address (a webhook) or let the bot ask for them. Asking needs no open port, no public address and no TLS certificate, which suits a gateway bound to 127.0.0.1. Each request waits up to `poll_seconds` (30 by default) and returns at once when a message arrives, so replies are immediate. The read timeout is ten seconds longer than the poll, so a quiet poll is not mistaken for a network failure.

`get_updates` is given an offset one past the last update, which tells Telegram those updates are handled; a restart therefore does not replay old messages.

Only text messages are handled; photos and stickers are skipped for now.

## Sending

Telegram refuses messages over 4096 characters, so long answers are split at line breaks into parts of at most 4000. Messages are sent as plain text, with no Markdown, because a desk's answer can contain characters that Telegram's Markdown would misread and refuse.

The bot's library is used directly (`telegram.Bot`) rather than its `Application` framework, because the gateway already has its own event loop and background workers; a plain loop of `get_updates` is easier to follow and to stop.
