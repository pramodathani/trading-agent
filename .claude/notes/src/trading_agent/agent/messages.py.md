# messages.py

The conversation is stored in a form that belongs to no model, and each backend converts it into its own wire format. That is what lets the model router (milestone 4) hand a conversation from Claude to Qwen to Gemma without losing it.

Ollama gives tool calls no identifier; OpenAI and Claude do. `ToolCall.new` creates one when the backend has none, so events and results can always be matched to their call.
