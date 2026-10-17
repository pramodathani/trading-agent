# templates/agents/

The four starter subagents from the plan, copied into `workspace/shared/agents/` the first time that folder is created, after which they belong to the user. A starter the user deletes is not brought back.

| Subagent | Model | Tools | Purpose |
|---|---|---|---|
| news_reader | qwen | web_search, web_fetch, search_knowledge, get_time | dated news with sources, and what could move the price |
| market_researcher | qwen | quotes, candles, instruments, bash_run, web, knowledge | levels, trend, support and resistance, computed in python3 |
| trade_reviewer | the desk's order | read_file, search_sessions, orders, portfolio, candles, knowledge | checks a trade against TradingRules.md and the desk's history; never trades |
| strategy_tester | the desk's order | candles, bash_run, bash_check, read_file, knowledge, time | tests a simple rule on daily candles without look-ahead, with costs and limitations |

The two readers use Qwen so routine reading does not use the Max subscription's limits; the two that need judgement inherit the desk's order, which starts with Claude. If a named backend is removed from trading_agent.toml, the subagent falls back to the desk's order with a note.
