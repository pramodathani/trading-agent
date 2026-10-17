# tool.py

Each tool describes its arguments as a pydantic model. One definition then serves two purposes: `model_json_schema()` gives the JSON schema the AI model is shown, and `model_validate` checks the arguments the AI model sends before any code runs. Argument models use `extra='forbid'`, so a misspelt argument name is reported to the model instead of being ignored.

`input_schema` drops pydantic's `title` key and always includes `properties` and `required`, because some servers reject a schema without them.

A result can carry a picture (`image`, a `messages.MessageImage` with its media type), used by `browser_screenshot`, `view_image` and MCP tools. Until attachments part 2 this was `image_png: bytes`, which could only hold PNG; `view_image` sends the resized JPEG that `ImagePreparer` makes, because a 1568-pixel photo saved as PNG can pass the 5 MB per-picture limit of the Claude API. Each backend passes the picture on in its own way: Claude receives it as an MCP image block with the right `mimeType`, Ollama as the tool message's `images`, and an OpenAI-compatible server as a user message after the tool results (see that backend's note).

`picture_desk_path` is separate from `image` on purpose. The image is what the model sees, often resized; the path is where the original is saved, relative to the desk folder, so the executor can put it in the `tool_result` event and the web page can show it in the tool's card through `GET /api/desks/{desk}/pictures/{path}`. A picture outside the desk folder, such as one from an MCP server, has no path and simply is not shown in the card. `send_image` returns no path, because its picture already appears in the chat as the desk's message and showing it twice was noise.
