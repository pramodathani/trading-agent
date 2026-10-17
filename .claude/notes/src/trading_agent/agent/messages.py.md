# messages.py

The conversation is stored in a form that belongs to no model, and each backend converts it into its own wire format. That is what lets the model router (milestone 4) hand a conversation from Claude to Qwen to Gemma without losing it.

Ollama gives tool calls no identifier; OpenAI and Claude do. `ToolCall.new` creates one when the backend has none, so events and results can always be matched to their call.

## Pictures on user messages, since 2026-10-17

`MessageImage` is a picture already prepared for a model (upright, at most 1568 pixels, JPEG or PNG). `ConversationMessage.images` carries them on user messages. The older `image_png` stays for tool results, such as browser screenshots, which are always PNG and one per result; merging the two was not worth changing every tool.

`base64_data` lives on the picture because all three APIs want base64.

Since attachments part 2 a tool message carries its picture as `image: MessageImage` rather than `image_png: bytes`, so a tool can return a JPEG as well as a PNG and every backend learns the media type from the same field.
