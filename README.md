# trading-agent

An always-on, multi-trader AI trading agent on the `tradingmachine` library and UBI. Four starter traders (general, intraday, scalper and positional), and any you create from the web page, the phone, Telegram or the terminal, each run their own agent with their own mandate, persona, models, schedule and memory, and every order from every trader goes through one risk engine that enforces the hard limits in `workspace/shared/TradingRules.md`. Models are Claude through the Max subscription, and Gemma and Qwen on Ollama, with automatic fallback.

## Using it

| What | Where |
|---|---|
| Web page | <http://127.0.0.1:8120>, with the token from `TRADING_AGENT_GATEWAY_ACCESS_TOKEN` in `.env` |
| Telegram | See `docs/telegram_setup.md` |
| Going live | See `docs/going_live.md` |
| The documentation site | `.venv/bin/mkdocs serve -a 127.0.0.1:8130`, then <http://127.0.0.1:8130/trading-agent/> |
| Create, retire or restore a trader | **New trader** on the Traders page, `bin/trading-agent traders new NAME --mandate TEXT`, or `/create NAME MANDATE` in Telegram |
| Your instructions to the traders | `workspace/shared/Agents.md`, `User.md`, `TradingRules.md`, and each trader's `Persona.md`, editable on the Files page |

## Commands

| Task | Command |
|---|---|
| Is everything in place? | `bin/trading-agent doctor` |
| Ready to trade live? | `bin/trading-agent preflight` |
| Run the gateway by hand | `bin/trading-agent serve` (the service normally runs it) |
| The service | `systemctl --user status trading-agent`, `restart`, `stop`; log with `journalctl --user -u trading-agent -f` |
| Install the service on a new machine | `systemctl --user link $PWD/deploy/trading-agent.service && systemctl --user enable --now trading-agent` |
| Message a trader from a terminal | `bin/trading-agent send --trader intraday "What is your plan?"` |
| Proposals, checkpoints, skills | `bin/trading-agent proposals list`, `checkpoints list`, `skills list` |
| Packages and their apps | `bin/trading-agent packages install <folder>`, `apps list` |
| Telegram pairing | `bin/trading-agent pairing list`, `approve <code>`, `revoke <chat id>` |
| Tests | `.venv/bin/pytest` |
| Lint and format | `.venv/bin/ruff check . && .venv/bin/ruff format --check .` |
| Build the web page | `source ~/.nvm/nvm.sh && cd frontend && npm run build` |

## Layout

```text
trading-agent/
├── bin/trading-agent        the command
├── src/trading_agent/       the gateway, traders, backends, tools, risk engine, scheduling, channels
├── frontend/                the web page (React and Vite), served from frontend/dist
├── workspace/               your files and the traders' memory, journals and sessions
├── packages/                package sources, such as packages/sridhara
├── deploy/                  the systemd unit and SearXNG
├── docs/                    the Telegram and going-live guides
└── tests/
```

The reasoning behind each source file is in `.claude/notes/`, one note per file.
