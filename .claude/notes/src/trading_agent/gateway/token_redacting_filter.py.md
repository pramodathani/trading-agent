# token_redacting_filter.py

On 2026-10-16 the first live test showed uvicorn writing the WebSocket address, including `?token=...`, to its log. Anyone who could read the log could have controlled the gateway. This filter replaces the value with `***` in both the message and its `%` arguments, because uvicorn passes the address as an argument.

It must be installed after `uvicorn.Config(...)` is created, because creating the configuration sets up uvicorn's logging. For that reason `application.py` builds `uvicorn.Config` and `uvicorn.Server` itself instead of calling `uvicorn.run`.

The general secret redactor for logs, the journal and tool output comes in milestone 8; this filter covers only the gateway's token.

## Bot tokens (milestone 19)

python-telegram-bot sends its requests through httpx, which logs every request at INFO, and Telegram's addresses contain the bot token as `/bot<token>/`. The filter now masks that part too, and is attached to the httpx and telegram loggers and to the root logger's handlers. The root handlers matter because a logger's own filters do not see records from its child loggers, such as telegram.bot. httpx passes the address as an httpx.URL object, not a string, so every non-number argument is turned into text before masking.
