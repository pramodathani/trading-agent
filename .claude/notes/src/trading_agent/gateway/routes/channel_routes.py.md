# channel_routes.py

Feeds the Channels page. Approval goes through the running channel when there is one, so the chat is told it is paired; when Telegram is off, approval still works on the file, so a chat can be paired before Telegram is switched on.

Revoking does not message the chat; the bot simply treats it as a stranger again.
