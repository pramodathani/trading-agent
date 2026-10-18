---
hide:
  - navigation
---

# trading-agent

<div class="hero" markdown>

<p class="lead"><code>trading-agent</code> is an always-on AI trading agent that trades on its own, without asking anyone to approve its orders. It runs four <strong>desks</strong> side by side: <em>general</em>, <em>intraday</em>, <em>scalper</em> and <em>positional</em>. Each desk has its own persona, models, schedule and memory, and every order from every desk passes through <strong>one risk engine</strong> that enforces the hard limits you write in <code>TradingRules.md</code>. It trades through <a href="https://pramodathani.github.io/tradingmachine/">tradingmachine</a> and the <a href="https://pramodathani.github.io/unified_broker_interface/">Unified Broker Interface</a> (UBI), and thinks with Claude through the Max subscription, with DeepSeek when Claude is unavailable, and with Gemma and Qwen on this machine.</p>

</div>

<figure class="diagram">
--8<-- "docs/assets/diagrams/desks.svg"
<figcaption>Orange dots are orders from the four desks; every one reaches the same risk engine, and only approved ones reach UBI. The blue dot is a refusal: the scalper may not trade a stock the intraday desk already holds.</figcaption>
</figure>

## Start here

The site is split into tabs along the top. If you are about to trade live, read the second card first.

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } **Get started**

    ---

    Install it, fill in `trading_agent.toml` and `.env`, run the doctor, and start the service.

    [:octicons-arrow-right-24: Installation](get-started/index.md)

-   :material-flag-checkered:{ .lg .middle } **Going live**

    ---

    The plan for the first trading day: the last dry-run checks, the switch to live orders, and every way to stop.

    [:octicons-arrow-right-24: Going live](going_live.md)

-   :material-monitor-dashboard:{ .lg .middle } **Using it**

    ---

    The web page, talking to a desk, answering its questions, steering and stopping a turn, Telegram, and every command.

    [:octicons-arrow-right-24: The web page](using/index.md)

-   :material-shield-check:{ .lg .middle } **Desks and risk**

    ---

    The four desks, the files that instruct them, the risk engine's limits, and how an order travels.

    [:octicons-arrow-right-24: The desks](desks/index.md)

-   :material-brain:{ .lg .middle } **The agent**

    ---

    Models and fallback, the 49 tools, memory and compression, skills, subagents, scheduling and extensions.

    [:octicons-arrow-right-24: How a desk thinks](agent/index.md)

-   :material-layers-triple:{ .lg .middle } **Architecture**

    ---

    The gateway and its parts, the HTTP API, the security model and the reasons behind the design.

    [:octicons-arrow-right-24: How it fits together](architecture/index.md)

</div>

## What it does, in one table

The table below lists the pieces a newcomer usually asks about first, and where each is explained.

| You want to know | The short answer | Read |
|---|---|---|
| Who approves the orders? | Nobody. The risk engine's hard limits are the only gate. | [The risk engine](desks/risk-engine.md) |
| Does it ever ask me? | Only when it chooses to ask a question or show a plan, and before any tool you list in `[approvals]`, which is only `flatten_desk` on this machine. It never waits for the answer. | [Questions, plans and permissions](using/questions-and-permissions.md) |
| Which models does it use? | Claude through your Max subscription, never the API; then DeepSeek V4 Pro, then Qwen and Gemma on Ollama when Claude is unavailable. | [Models](agent/models.md) |
| How do I talk to it? | The web page at <http://127.0.0.1:8120>, Telegram, or `bin/trading-agent send`. | [Using it](using/index.md) |
| How do I stop it? | Stop a turn, pause a desk, flatten a desk, or fire the kill switch. | [Going live](going_live.md#how-to-stop) |
| What can it change? | Its own notes, memory and skills. It only proposes changes to your files. | [Your files](desks/your-files.md) |
| Does it keep running? | Yes. It is a systemd user service that restarts after a crash and resumes every conversation. | [The service](get-started/service.md) |

## A first taste

The commands below check the setup, ask a desk a question from the terminal, and show the state of the service. The output of the second command is real, from Saturday 17 October 2026, when the market was closed.

```console
$ bin/trading-agent doctor
$ bin/trading-agent send --desk scalper "What time is it in India? Use your get_time tool."
  [tool] get_time({})
It's 14:04 IST on Saturday 17 October 2026 in India.
$ systemctl --user status trading-agent
```
