# First run

The first run checks the machine, starts the gateway by hand, and sends a trader its first message.

## 1. The doctor

The doctor checks everything the agent depends on and explains each problem it finds:

```bash
bin/trading-agent doctor
```

It checks Python, the access token, UBI, each model backend, the Claude token and the absence of `ANTHROPIC_API_KEY`, the DeepSeek key, SearXNG, Telegram, the limits in TradingRules.md, the files the traders read for planted instructions, the exchange calendar, the MCP servers, the bash sandbox and Chrome. Each line starts with `[ ok ]`, `[warn]` or `[FAIL]`.

## 2. The gateway

Start the gateway in a terminal:

```bash
bin/trading-agent serve
```

On its first start it creates the workspace: your files in `workspace/shared/` and one folder per trader in `workspace/traders/`. Each trader then starts, resumes its saved session if there is one, and waits for a message.

## 3. The web page

Open <http://127.0.0.1:8120>. The page asks for the access token, the value of `TRADING_AGENT_GATEWAY_ACCESS_TOKEN` in `.env`, and keeps it in the browser. The Traders page then shows the four traders, and the header says **DRY RUN**.

## 4. A first message

Choose a trader in the header, open **Chat**, and send `/status`, which is answered by code without a model. Then ask something the trader must think about, such as:

> What time is it in India? Use your get_time tool.

The tool call appears as a card, and the answer as the text is written. The same works from a terminal:

```bash
bin/trading-agent send --trader general "What time is it in India?"
```

When this works, stop the gateway with Ctrl+C and set it up as [the service](service.md).
