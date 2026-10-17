# telegram_commands.py

The plan asks for /status, /positions, /pnl, /pause and /kill to be answered by code with no model. These are the commands needed when things go wrong, which is exactly when models may be unavailable or slow. /desk, /resume, /help and /start are added because a chat needs them.

## Names that clash with the desks' own commands

/status here describes every desk and the account, because on a phone the whole picture is what matters; the desk's own /status, which describes one desk's models, is still on the web page. Every other slash command, such as /stop, /usage, /model and /compact, is passed to the chat's desk unchanged.

## /kill

It needs the word CONFIRM, as the plan says, so a tap on a suggested command cannot fire it. It calls the same kill switch as the loss limit and the web page, so in dry_run mode the flatten is a dry run. It is left out of the command menu suggested in docs/telegram_setup.md for the same reason.

## /pause all

Pausing every desk from a phone in one message is the gentle alternative to the kill switch: nothing is flattened, but no desk asks a model until /resume.

Group chats add `@botname` to commands; that suffix is ignored. docs/telegram_setup.md tells the user to stop the bot joining groups anyway.

## Command menu and help, since 2026-10-18

`menu()` gives the list Telegram shows when the user types a slash. It mixes Telegram's own commands with the desk commands that are passed through, because the user cannot tell the two apart on the phone. Telegram requires names without the slash, lowercase, at most 32 characters, and descriptions of 1 to 256 characters; a test checks this.

`/help` now lists the desk commands too, instead of naming only three of them.

The Telegram versions of `/status`, `/help`, `/pause` and `/resume` shadow the desk versions of the same names. That is deliberate, because the Telegram ones cover every desk and the account, which is what matters on the phone.

## /approve and /deny, since 2026-10-18

These copy the typed approvals of OpenClaw (`/approve`) and Hermes (`/approve`, `/deny`). They decide a permission request, which today means a held `flatten_desk`, without the buttons, for a Telegram client where buttons fail or were scrolled far away.

They call `UserRequestResponder.decide_permission` with `via='telegram'`, the same path as the buttons, so the decision, the run of the held call, the standing grant for "always" and the message to the desk all behave identically. The buttons message is closed by the `user_response` event as usual.

The id may be left out when one permission request is waiting, which is the usual case, and may be shortened to its last six characters, the random part of `20261018-093012-a1b2c3`. When several are waiting and none is named, the reply lists them with their short ids rather than guessing, because approving the wrong flatten could close the wrong desk's positions.

A first word that is not a waiting id is read as the reason for `/deny` (or "always" for `/approve`), so `/deny too risky` works with one request waiting.

A request past its expiry but not yet marked expired is refused by the responder, and the error is passed on in the reply.

Known limit: when a desk's question is waiting for a typed "Other" answer, the channel takes the next text as that answer before it checks for commands (`telegram_channel.py`), so `/approve` typed then is taken as the answer. That order was chosen with the question feature and is unchanged.
