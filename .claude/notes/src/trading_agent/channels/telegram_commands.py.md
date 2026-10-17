# telegram_commands.py

The plan asks for /status, /positions, /pnl, /pause and /kill to be answered by code with no model. These are the commands needed when things go wrong, which is exactly when models may be unavailable or slow. /desk, /resume, /help and /start are added because a chat needs them.

## Names that clash with the desks' own commands

/status here describes every desk and the account, because on a phone the whole picture is what matters; the desk's own /status, which describes one desk's models, is still on the web page. Every other slash command, such as /stop, /usage, /model and /compact, is passed to the chat's desk unchanged.

## /kill

It needs the word CONFIRM, as the plan says, so a tap on a suggested command cannot fire it. It calls the same kill switch as the loss limit and the web page, so in dry_run mode the flatten is a dry run. It is left out of the command menu suggested in docs/telegram_setup.md for the same reason.

## /pause all

Pausing every desk from a phone in one message is the gentle alternative to the kill switch: nothing is flattened, but no desk asks a model until /resume.

Group chats add `@botname` to commands; that suffix is ignored. docs/telegram_setup.md tells the user to stop the bot joining groups anyway.
