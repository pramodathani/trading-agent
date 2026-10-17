# telegram_check.py

Telegram's API addresses contain the bot token, and httpx includes the address in its exception messages. The check therefore reports only the exception's type, never its text, so a doctor report pasted somewhere cannot leak the token.

Telegram off with no token is OK, because Telegram is optional. A working token with Telegram switched off is a warning, because the user has probably forgotten `enabled = true`.
