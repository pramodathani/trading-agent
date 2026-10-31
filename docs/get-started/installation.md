# Installation

trading-agent is a Python 3.14 project with a React web page. The table below lists what it needs on the machine, and what each piece is for.

| Needed | What for | Check |
|---|---|---|
| Python 3.14 | The gateway and the traders | `python3.14 --version` |
| UBI on 127.0.0.1:8080 and the `tradingmachine` project beside this one | Market data and orders | `bin/trading-agent doctor` |
| Ollama with `gemma4:31b` and `qwen3.8:27b` | The local models | `ollama list` |
| Claude Code and a Max subscription | The Claude backend | `claude --version` |
| `bwrap` (bubblewrap) | The traders' bash sandbox | `bwrap --version` |
| Google Chrome | The traders' browser | `google-chrome --version` |
| Node.js through nvm | Building the web page | `source ~/.nvm/nvm.sh && node --version` |
| Docker | The local SearXNG search server | `docker compose ps` |

## The Python environment

From the project folder, create the virtual environment and install the project with its development and documentation extras:

```bash
python3.14 -m venv .venv
.venv/bin/pip install -e ../tradingmachine
.venv/bin/pip install -e ".[development,docs]"
```

The browser tools drive the installed Google Chrome through Playwright, so Playwright downloads no browser of its own.

## The Claude token

Claude is used through your Max subscription, never through the API. Create a one-year subscription token once, and keep it in `.env` as `TRADING_AGENT_CLAUDE_CODE_OAUTH_TOKEN`:

```bash
claude setup-token
```

!!! danger "Never set ANTHROPIC_API_KEY"
    If `ANTHROPIC_API_KEY` is set, Claude Code bills the API instead of your subscription. The Claude backend removes it from the environment of every Claude Code process it starts, and the doctor fails if it is set.

## The DeepSeek key

DeepSeek is the second model of every trader, after Claude. It is paid per token, so it needs an API key from the DeepSeek platform, kept in `.env`:

```text
DEEPSEEK_API_KEY=sk-...
```

Without the key, the traders skip DeepSeek and fall back from Claude straight to Qwen.

## Web search

The `web_search` tool asks a local SearXNG server, which `docker-compose.yml` starts on port 4001:

```bash
docker compose up -d
```

## The web page

The gateway serves the built page from `frontend/dist`, so build it once after installing and again after changing it:

```bash
source ~/.nvm/nvm.sh && cd frontend && npm install && npm run build
```

Next, fill in the [configuration](configuration.md).
