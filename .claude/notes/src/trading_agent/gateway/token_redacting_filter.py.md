# token_redacting_filter.py

On 2026-10-16 the first live test showed uvicorn writing the WebSocket address, including `?token=...`, to its log. Anyone who could read the log could have controlled the gateway. This filter replaces the value with `***` in both the message and its `%` arguments, because uvicorn passes the address as an argument.

It must be installed after `uvicorn.Config(...)` is created, because creating the configuration sets up uvicorn's logging. For that reason `application.py` builds `uvicorn.Config` and `uvicorn.Server` itself instead of calling `uvicorn.run`.

The general secret redactor for logs, the journal and tool output comes in milestone 8; this filter covers only the gateway's token.
