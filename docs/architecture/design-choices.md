# Design choices

The table below lists the main decisions, what was chosen, and why.

| Question | Choice | Why |
|---|---|---|
| Who approves orders? | Nobody; hard limits in code | You asked for an agent that never stops for a human. The limits are the safeguard instead of a person |
| How does a desk ask you something? | Questions, plans and permission requests are saved, the turn ends, and your answer arrives later as a message | A desk waiting for an answer would stop reacting to the market; an unanswered request holds nothing up |
| Which actions need permission? | Only the tools in `[approvals]`, enforced by the harness, and only `flatten_desk` today | A rule the model could skip is no rule; a permission that lapses after five minutes cannot act on stale prices |
| What answers when Claude cannot? | DeepSeek V4 Pro, then Qwen, then Gemma, switching only when Claude refuses | DeepSeek has Claude's 1,000,000-token window; the local models are free and always there |
| How is Claude used? | Claude Code through the Agent SDK, on the Max subscription | The subscription may not be used through the API directly; Claude Code with a setup token is the documented way for scripts |
| One agent or several? | Four independent desks in one gateway, sharing one risk engine | Each style needs its own pace, models and memory, but the account and its limits are shared |
| What does the scalper do itself? | Decides; UBI's bracket orders execute | A model takes seconds per decision, so it cannot trade tick by tick |
| How do the desks hear about the market? | A watcher loop with no model, polling UBI | tradingmachine has no streaming; a loop with no model costs nothing between events |
| Where do instructions live? | Markdown files you edit, read at every turn | Plain files are easy to read, diff, version and correct |
| What may the agent change? | Only its own notes, memory and skills | Your instructions and limits stay yours; changes to them are proposals |
| How is a mistake undone? | Checkpoints of the desk's own files, before every write | Any change by the desk, the curator or you can be rolled back |
| How do messages reach a busy desk? | Steering at the next tool round, and /stop that skips the queue | A long turn should not make you wait minutes to change course |
| How are other apps added? | Packages with an app.toml, run as their own services | Nothing outside trading-agent's own code runs in the gateway |
| How does it stay up? | A systemd user service with Restart=always | The system's own supervisor restarts it and starts it at boot |
| How do Telegram messages arrive? | Long polling, not a webhook | No open port, no public address and no certificate are needed |
