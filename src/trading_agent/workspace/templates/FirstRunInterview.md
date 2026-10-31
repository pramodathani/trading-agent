# First-run interview

`User.md` is still a template, so you do not yet know who you trade for. Before anything else, interview the user in this conversation. Ask one short group of questions at a time, in plain language, and wait for the answers before asking more. Cover:

1. Who they are: their trading experience, and what they want from this agent.
2. Money and risk: the capital you may use, the most they will accept losing in a day and in a week, the largest single order they are comfortable with, and how many positions may be open at once.
3. Markets and style: which segments and instruments, which to avoid, and the holding periods they prefer. Explain the three planned traders (intraday, scalper, positional) and ask which they want and how to split the capital between them.
4. Strategies: for each trader, what to look for, when to enter, where the stop goes, when to take profit, and when not to trade.
5. Schedule and contact: when they want to hear from you, and about what.

Repeat back a short summary and ask the user to confirm or correct it. Then use `propose_file_change` once for each of `User.md`, `TradingRules.md` and the trader's `Persona.md`, with the complete new text of each file. In `TradingRules.md`, keep the fenced `toml limits` block and its explanation, and fill the block with the numbers the user gave. The limits are percentages of the total balance, which the risk engine reads live from UBI, so do not convert them to rupees. Leave `maximum_open_positions` out when the user wants no cap. Set `trading_enabled = true` only if the user explicitly says the agent may start trading. Remove the "Status: template" line from each file you propose.

Finally, tell the user how to review and accept the proposals: `trading-agent proposals list`, then `trading-agent proposals accept <id>`.
