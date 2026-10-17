# subagent_prompt_builder.py

A subagent's prompt is a short code-written header (who it works for, the mode, that its reply is all the desk sees, that it cannot ask questions, facts only from tools, outside text is data) and then its definition's instructions. It does not include the desk's workspace files, to keep the prompt small for local models; a definition that needs the rules reads TradingRules.md itself, as the starter trade_reviewer does. Its build() returns a SystemPrompt like the desk's PromptBuilder, so the same turn runners work with either.
