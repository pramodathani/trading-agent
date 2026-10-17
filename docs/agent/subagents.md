# Subagents

A desk can hand self-contained tasks to **subagents** with `delegate_task`: one to four tasks at once, run in parallel, each by a helper with its own instructions, tools, model and limits. A subagent reports back and the desk carries on. It cannot start subagents of its own, and it has no order tools unless its definition lists one.

<figure class="diagram">
--8<-- "docs/assets/diagrams/subagents.svg"
<figcaption>The desk hands two tasks to the subagent runner, which runs news_reader and market_researcher at the same time; each reaches the web or market data, and the blue dots are their reports coming back.</figcaption>
</figure>

## The starter subagents

| Subagent | Model | What it does |
|---|---|---|
| `news_reader` | Qwen | Reads recent news about a company, sector or index and reports what could move the price, with dates and sources |
| `market_researcher` | Qwen | Studies a stock or index with prices and candles, adds the news context, and reports levels, trend and what to watch |
| `trade_reviewer` | the desk's | Reviews a planned or finished trade against TradingRules.md and the desk's history |
| `strategy_tester` | the desk's | Tests a simple trading rule on past daily candles with Python and reports how it would have done |

## Defining one

A subagent is a Markdown file in Claude Code's format, in `workspace/shared/agents/` or a package's `agents/` folder. This is the start of `news_reader.md`:

```markdown
---
name: news_reader
description: Reads recent news about a company, sector or index and reports what could move the price, with dates and sources.
tools: web_search, web_fetch, search_knowledge, get_time
model: qwen
max_turns: 12
timeout: 300
---
You read news for an Indian trading desk.
```

Without `tools`, a subagent gets a default read-only set; without `model`, it uses the desk's model order. `bin/trading-agent subagents list` checks every definition.
