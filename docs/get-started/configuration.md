# Configuration

trading-agent reads two files from the project folder. `trading_agent.toml` holds the settings and can be committed to git. `.env` holds the secrets and never leaves this machine. A typing mistake in either is reported by name when the program starts, because every value is checked against its type and range.

## Secrets in .env

Each secret can also be given as an environment variable of the same name, which then takes precedence over `.env`. A backend's own key, such as `DEEPSEEK_API_KEY`, is read by exactly the name its `api_key_variable` gives, without the `TRADING_AGENT_` prefix.

| Variable | What it is | Needed |
|---|---|---|
| `TRADING_AGENT_GATEWAY_ACCESS_TOKEN` | The token every web page and API request must show | Yes |
| `TRADING_AGENT_CLAUDE_CODE_OAUTH_TOKEN` | The Max subscription token from `claude setup-token` | For Claude |
| `TRADING_AGENT_OPENAI_API_KEY` | A key for OpenAI-compatible servers that need one | No |
| `DEEPSEEK_API_KEY` | DeepSeek's API key, named by `api_key_variable` in `[backends.deepseek]`; without it, DeepSeek is skipped | For DeepSeek |
| `TRADING_AGENT_WEBHOOK_TOKEN` | The token incoming webhooks must show; empty switches webhooks off | No |
| `TRADING_AGENT_TELEGRAM_BOT_TOKEN` | The bot token from BotFather | For Telegram |
| `TRADING_AGENT_SEARXNG_SECRET` | SearXNG's own secret, read by docker-compose | For web search |

## trading_agent.toml

### The top level

| Setting | Default | Meaning |
|---|---|---|
| `mode` | `"dry_run"` | `"dry_run"` sends every order to UBI as a dry run; `"live"` sends real orders |
| `workspace_directory` | `"workspace"` | Your files and the desks' memory, journals and sessions |
| `tradingmachine_environment_file` | required | tradingmachine's `.env`, for UBI and MongoDB |
| `mcp_servers_file` | `"mcp_servers.json"` | The MCP servers every desk can use |
| `market_calendar_directory` | none | UBI's folder of yearly exchange calendars; without it only weekends are known |

### [gateway]

| Setting | Default | Meaning |
|---|---|---|
| `host` | `"127.0.0.1"` | The address to listen on; 127.0.0.1 keeps it reachable from this machine only |
| `port` | `8120` | The port of the web page, the API and the event stream |
| `frontend_directory` | `"frontend/dist"` | The built web page |

### [[desks]]

One table per desk. The four desks of this machine are in the [desks section](../desks/index.md).

| Setting | Default | Meaning |
|---|---|---|
| `name` | required | Used in folder names, order tags and the web page |
| `enabled` | `true` | Whether the desk starts with the gateway |
| `backend_order` | `[]` | The models the desk may use, most preferred first; empty means commands only |
| `heartbeat_minutes` | none | Minutes between heartbeats while NSE equities trade; each heartbeat is a model turn |
| `rollover_time` | `"15:45"` | When, on trading days, the session is summarised and a new one starts |
| `scheduled_checks` | `[]` | Times on trading days when the desk is woken to do what its Persona.md says for that time |

### [backends.<name>]

One table per model a desk can use. [Models](../agent/models.md) shows the five on this machine.

| Setting | Default | Meaning |
|---|---|---|
| `kind` | required | `"claude_code"`, `"deepseek"`, `"ollama"` or `"openai_compatible"` |
| `base_url` | none | The server's address, needed by every kind except claude_code |
| `model` | required | The model's name on its server, such as `"opus"` or `"deepseek-v4-pro"` |
| `context_window` | required | How many tokens of context the model is given |
| `thinking` | `true` | Whether the model reasons before answering, where it can |
| `effort` | Claude Code's default | For claude_code, how hard Claude thinks: `"low"`, `"medium"`, `"high"`, `"xhigh"` or `"max"` |
| `api_key_variable` | `TRADING_AGENT_OPENAI_API_KEY` | The `.env` entry holding this backend's key, such as `"DEEPSEEK_API_KEY"` |
| `vision` | `true` | Whether the model can read pictures; when false, pictures are left out and the model is told so |
| `other_models` | `[]` | Other models of the same provider that the chat page's model menu offers, such as `"claude-haiku-5-5"` |
| `rupees_per_million_prompt_tokens`, `rupees_per_million_completion_tokens` | none | Prices, so `/usage` can show costs |
| `usd_per_million_cache_hit_tokens`, `usd_per_million_cache_miss_tokens`, `usd_per_million_completion_tokens` | none | For deepseek, the peak-hour prices in dollars, split by whether DeepSeek's cache held the prompt |
| `peak_hours_utc` | `[]` | For deepseek, the weekday periods charged at peak prices, such as `"01:00-04:00"`, in UTC |
| `off_peak_price_factor` | `1.0` | For deepseek, what off-peak prices are as a share of peak prices, such as `0.5` |

### [agent]

| Setting | Default | Meaning |
|---|---|---|
| `maximum_rounds` | `20` | The most model calls in one turn |
| `maximum_identical_tool_calls` | `3` | How often one tool may be called with the same arguments in a turn |
| `tool_timeout_seconds` | `60` | How long one tool call may run |
| `compression_threshold` | `0.7` | The share of the context window at which, before the next turn, the desk saves what matters and its conversation is summarised |
| `emergency_compression_threshold` | `0.85` | The share at which a conversation is compressed in the middle of a long turn |

### [sandbox]

| Setting | Default | Meaning |
|---|---|---|
| `command_timeout_seconds` | `120` | How long one bash command may run |
| `maximum_output_characters` | `20000` | How much of a command's output the model sees |
| `hidden_paths` | the credential folders, every `.env`, UBI's folder and Docker's socket | Replaced by empty ones inside the sandbox |
| `passed_environment` | `[]` | Environment variables passed into the sandbox, which otherwise starts empty |

### [web], [browser], [risk], [skills]

| Setting | Default | Meaning |
|---|---|---|
| `web.searxng_base_url` | `"http://127.0.0.1:4001"` | The local search server |
| `web.search_result_limit` | `8` | The most results one search returns |
| `web.fetch_timeout_seconds` | `20` | How long fetching one page may take |
| `web.maximum_page_characters` | `15000` | How much of a page the model sees |
| `browser.headless` | `true` | Turn it off to watch a desk browse |
| `browser.navigation_timeout_seconds` | `30` | How long opening a page may take |
| `browser.maximum_elements` | `150` | The most clickable elements in one snapshot |
| `browser.maximum_text_characters` | `8000` | How much visible text one snapshot returns |
| `risk.ownership_grace_minutes` | `30` | How long a desk keeps its claim on a stock it ordered but does not yet hold |
| `risk.margin_rates.*` | 0.2 intraday, 0.15 index derivatives, 0.4 stock derivatives, 0.47 commodity, 0.1 currency | Used to estimate an order's margin |
| `skills.archive_after_days` | `30` | Days a desk's own skill may go unused before the curator archives it |

### [telegram]

| Setting | Default | Meaning |
|---|---|---|
| `enabled` | `false` | Whether the gateway talks to Telegram |
| `default_desk` | the first desk | The desk a paired chat talks to at first |
| `notifications` | all ten kinds | What is pushed to your phone; see [Telegram](../telegram_setup.md#7-choose-what-is-pushed-to-you) |
| `poll_seconds` | `30` | How long one request to Telegram waits for a message |

### [approvals]

These settings choose which of the desks' actions wait for your permission, as [Questions, plans and permissions](../using/questions-and-permissions.md#permission-prompts) explains.

| Setting | Default | Meaning |
|---|---|---|
| `tools` | `[]` | The tools whose every call by a desk or a subagent waits for your permission; `["flatten_desk"]` on this machine |
| `expiry_minutes` | `5` | How long a permission request stays open before it lapses and the action is not run, from 1 to 1440 |

The trading limits are not here. They live in `workspace/shared/TradingRules.md`, described in [The risk engine](../desks/risk-engine.md), so the desks read them as part of their instructions.
