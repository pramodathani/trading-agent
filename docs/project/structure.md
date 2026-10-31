# Repository structure

```text
trading-agent/
├── bin/trading-agent          the command; with no subcommand, the terminal program
├── src/trading_agent/         the gateway and everything it runs
├── frontend/                  the web page: React 19, TypeScript, Vite 8
│   └── android/               the Android app around it (Capacitor 8)
├── workspace/                 your files and the traders' memory, journals and sessions
├── packages/                  package sources, such as packages/sridhara
├── deploy/                    the systemd unit, and SearXNG's settings
├── docs/                      this site's pages
├── scripts/                   the API reference generator for this site
├── tests/                     the pytest suite
├── trading_agent.toml         the settings
├── mcp_servers.json           the MCP servers
├── mkdocs.yml                 this site's configuration
└── .claude/notes/             one note per source file, with the reasoning behind it
```

## The source packages

| Package | What it holds |
|---|---|
| `runtime` | The trader runtime, the base turn runner, the event bus, triggers, slash commands and the steering inbox |
| `agent` | The agent loop and its turn runner, the conversation, the prompt builder, context compression, the context-usage breakdown and the loop guard |
| `backends` | The Ollama, OpenAI-compatible, DeepSeek and Claude Code backends, and the model router |
| `tools` | The 49 tools, the tool-call executor, the bash sandbox, the browser session and the address guard |
| `requests` | The traders' questions, plans and permission requests, the permission gate, the standing permissions and the expiry watcher |
| `attachments` | The attachment store, the readers for PDF, Word, Excel and text, and the picture preparer |
| `risk` | The trading limits, the risk engine, the risk ledger, the account snapshot and the kill switch |
| `trading` | The broker reader and the trader order book |
| `memory` | Sessions, the session keeper, session search and checkpoints |
| `skills` | The skill library, writer, usage tracker, curator and importer |
| `subagents` | Subagent definitions, the runner and their toolbox |
| `extensions` | MCP, packages, hooks, the injection scanner and apps |
| `knowledge` | The full-text knowledge base |
| `scheduling` | The market calendar, cron jobs and scheduler, built-in jobs, price alerts and the market watcher |
| `journal` | The trade journal, the journal reader, the usage tracker and the secret redactor |
| `channels` | Telegram: the API wrapper, pairing, commands, request buttons and notifications |
| `devices` | The Android app's notifications: the registered phones, the Firebase sender and the push channel |
| `gateway` | The FastAPI application, the access guard and the route groups |
| `configuration` | `trading_agent.toml` and `.env` |
| `doctor` | The doctor's checks and the going-live checks |
| `client` | The subcommands that are not `serve`, and the client behind `send` and `-p` |
| `terminal` | The terminal program: the gateway client, the event stream, the chat transcript, the chat screen with its side panel and request dock, and one screen per page |
| `workspace` | The workspace layout, its templates and proposals |

`application.py` holds the `Application` class that `__main__.py` runs, and `trader_builder.py` builds each trader from its configuration. The [API reference](../reference/trading_agent/index.md) has one page per module.
