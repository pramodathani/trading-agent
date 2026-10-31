# Gateway API

The gateway listens on 127.0.0.1:8120. Every route under `/api` except `/api/health` needs the access token, sent as `Authorization: Bearer <token>`; a missing or wrong token gets 401. The web page uses exactly these routes, so anything it does can also be scripted.

```bash
TOKEN=$(grep ^TRADING_AGENT_GATEWAY_ACCESS_TOKEN .env | cut -d= -f2-)
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8120/api/traders
```

## Health

| Method | Route | What it does | Token |
|---|---|---|---|
| <span class="method get">GET</span> | `/api/health` | Is the gateway running, and each trader's state | no |

## Traders

| Method | Route | What it does | Token |
|---|---|---|---|
| <span class="method get">GET</span> | `/api/traders` | Every trader's state, models and session | yes |
| <span class="method get">GET</span> | `/api/traders/{trader}` | One trader, with its persona | yes |
| <span class="method get">GET</span> | `/api/traders/{trader}/context` | How full the context window is, by category, and the trader's tools | yes |
| <span class="method get">GET</span> | `/api/traders/{trader}/commands` | The trader's slash commands and usable skills, each with its usage, what it does, and whether it is answered at once, beside the running turn, or queued; the web page's and the terminal's command menus read it | yes |
| <span class="method post">POST</span> | `/api/traders/{trader}/model` | Try one model first from now on, optionally another of its provider's models, or go back to the configured order, as `/model` does | yes |
| <span class="method post">POST</span> | `/api/traders/{trader}/messages` | Queue a message or slash command, with `attachment_ids` naming uploaded files; the answer arrives as events | yes |
| <span class="method post">POST</span> | `/api/traders/{trader}/attachments` | Upload one picture or document (a form with a `file` field); answers its attachment | yes |
| <span class="method get">GET</span> | `/api/traders/{trader}/attachments/{attachment}` | The uploaded file itself | yes |
| <span class="method get">GET</span> | `/api/traders/{trader}/pictures/{path}` | A picture inside the trader's folder, such as a screenshot in a tool card | yes |
| <span class="method post">POST</span> | `/api/traders/{trader}/pause` | Stop the trader asking its models | yes |
| <span class="method post">POST</span> | `/api/traders/{trader}/resume` | Start it again | yes |
| <span class="method post">POST</span> | `/api/traders/{trader}/flatten` | Cancel the trader's orders and close its positions, with a reason | yes |

## Creating, retiring and restoring traders

These routes change which traders exist, while the gateway runs. A refused request, such as a name that is invalid or already taken, an unknown backend, a check time that is not HH:MM, retiring the last running trader, or retiring one that still owns instruments or has open orders, gets status 400 with the reason in `detail`.

| Method | Route | What it does | Token |
|---|---|---|---|
| <span class="method get">GET</span> | `/api/trader-records` | Every trader's record, retired ones included, oldest first, each with `running` saying whether it runs now | yes |
| <span class="method post">POST</span> | `/api/traders` | Create a trader and start it; answers its record with status 201 | yes |
| <span class="method post">POST</span> | `/api/traders/{trader}/retire` | Stop a trader and mark it retired; its files stay | yes |
| <span class="method post">POST</span> | `/api/traders/{trader}/restore` | Bring a retired trader back, with its memory and sessions | yes |

The body of `POST /api/traders` holds the fields in the table below. The records have their own address, `/api/trader-records`, because `/api/traders/records` would be read as a trader named "records".

| Field | Needed | Meaning |
|---|---|---|
| `name` | yes | Lower-case letters, digits, hyphens and underscores, starting with a letter, at most 200 characters |
| `mandate` | yes | What the trader will trade and how, up to 4,000 characters |
| `backend_order` | no | The backends to use, most preferred first; empty or left out means `[traders] backend_order` |
| `heartbeat_minutes` | no | Minutes between heartbeats, from 1 to 240; `0` for none; left out or `null` for `[traders] heartbeat_minutes` |
| `scheduled_checks` | no | Times on trading days, as `"HH:MM"`, when the trader is woken |
| `introduce` | no | Whether to ask the trader at once to restate its mandate and propose how it will trade it; `true` unless given |

The example below creates a trader from a script.

```bash
curl -s -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "banknifty-momentum", "mandate": "Intraday momentum in Bank Nifty options, buying only, flat by 15:15", "heartbeat_minutes": 5, "scheduled_checks": ["09:20", "15:05"]}' \
  http://127.0.0.1:8120/api/traders
```

## Questions, plans and permissions

| Method | Route | What it does | Token |
|---|---|---|---|
| <span class="method get">GET</span> | `/api/requests` | The traders' waiting requests, or all of them with `status=all` | yes |
| <span class="method post">POST</span> | `/api/requests/{request}/answer` | Answer a question | yes |
| <span class="method post">POST</span> | `/api/requests/{request}/plan` | Approve a plan, or ask for changes | yes |
| <span class="method post">POST</span> | `/api/requests/{request}/permission` | Allow a held call once or always, or deny it | yes |
| <span class="method post">POST</span> | `/api/requests/{request}/dismiss` | Close a request without answering | yes |
| <span class="method get">GET</span> | `/api/permissions` | The standing "Always allow" permissions | yes |
| <span class="method post">POST</span> | `/api/permissions/revoke` | Make a trader ask again before using a tool | yes |

Each answer is handed to the trader as a new message; the trader never waited for it. An answer is recorded as given "via web" unless the client sends the header `X-Trading-Agent-Client: terminal`, which the terminal program does; any other value counts as web.

## The account

| Method | Route | What it does | Token |
|---|---|---|---|
| <span class="method get">GET</span> | `/api/account` | Balance, margin, day and week, each trader's profit, positions, owners, halts | yes |
| <span class="method get">GET</span> | `/api/orders` | UBI's order book: orders, trades or open parents | yes |
| <span class="method get">GET</span> | `/api/trader-orders` | Each trader's open orders in the trader order book | yes |
| <span class="method post">POST</span> | `/api/account/kill` | Fire the kill switch; needs {"confirm": "FLATTEN", "reason": ...} | yes |

## Memory and the journal

| Method | Route | What it does | Token |
|---|---|---|---|
| <span class="method get">GET</span> | `/api/traders/{trader}/sessions` | The trader's sessions | yes |
| <span class="method get">GET</span> | `/api/traders/{trader}/sessions/{session}` | One session's exchanges | yes |
| <span class="method get">GET</span> | `/api/traders/{trader}/summaries` | The daily summaries | yes |
| <span class="method get">GET</span> | `/api/traders/{trader}/notes` | The notes files | yes |
| <span class="method get">GET</span> | `/api/traders/{trader}/search` | Search the trader's memory | yes |
| <span class="method get">GET</span> | `/api/traders/{trader}/journal` | One day of the trader's journal | yes |
| <span class="method get">GET</span> | `/api/journal` | One day of the gateway's own journal | yes |

## Your files and proposals

| Method | Route | What it does | Token |
|---|---|---|---|
| <span class="method get">GET</span> | `/api/files` | The files you may edit | yes |
| <span class="method get">GET</span> | `/api/files/content` | One file's text | yes |
| <span class="method put">PUT</span> | `/api/files/content` | Save one file; TradingRules.md is checked first | yes |
| <span class="method get">GET</span> | `/api/proposals` | Every proposal, with its diff | yes |
| <span class="method post">POST</span> | `/api/proposals/{proposal}/accept` | Apply a proposal | yes |
| <span class="method post">POST</span> | `/api/proposals/{proposal}/reject` | Reject it | yes |

## Schedule

| Method | Route | What it does | Token |
|---|---|---|---|
| <span class="method get">GET</span> | `/api/traders/{trader}/jobs` | The trader's jobs with their next runs, and the latest runs | yes |
| <span class="method post">POST</span> | `/api/traders/{trader}/jobs` | Create a job | yes |
| <span class="method delete">DELETE</span> | `/api/traders/{trader}/jobs/{job}` | Delete one of your jobs | yes |
| <span class="method post">POST</span> | `/api/traders/{trader}/jobs/{job}/run` | Start a job now | yes |
| <span class="method get">GET</span> | `/api/traders/{trader}/alerts` | The trader's price alerts | yes |
| <span class="method delete">DELETE</span> | `/api/traders/{trader}/alerts/{alert}` | Remove one | yes |

## Extensions and checkpoints

| Method | Route | What it does | Token |
|---|---|---|---|
| <span class="method get">GET</span> | `/api/traders/{trader}/skills` | The trader's skills with their usage | yes |
| <span class="method get">GET</span> | `/api/subagents` | The subagent definitions | yes |
| <span class="method get">GET</span> | `/api/mcp` | Each MCP server's state and tools | yes |
| <span class="method get">GET</span> | `/api/packages` | The installed packages | yes |
| <span class="method get">GET</span> | `/api/traders/{trader}/checkpoints` | The trader's checkpoints | yes |
| <span class="method post">POST</span> | `/api/traders/{trader}/checkpoints/{checkpoint}/restore` | Restore one | yes |

## System

| Method | Route | What it does | Token |
|---|---|---|---|
| <span class="method get">GET</span> | `/api/usage` | Today's tokens per trader and model, and Claude's limits | yes |
| <span class="method get">GET</span> | `/api/configuration` | The configuration, with secrets masked | yes |

## Channels and apps

| Method | Route | What it does | Token |
|---|---|---|---|
| <span class="method get">GET</span> | `/api/channels` | Telegram's state, waiting codes and paired chats | yes |
| <span class="method post">POST</span> | `/api/channels/telegram/pairings/{code}/approve` | Pair the chat that was given a code | yes |
| <span class="method delete">DELETE</span> | `/api/channels/telegram/chats/{chat}` | Unpair a chat | yes |
| <span class="method get">GET</span> | `/api/devices` | Whether app notifications are on, and the registered phones, without their Firebase tokens | yes |
| <span class="method post">POST</span> | `/api/devices` | Register a phone's Firebase token for notifications | yes |
| <span class="method delete">DELETE</span> | `/api/devices/{device}` | Remove a phone | yes |
| <span class="method post">POST</span> | `/api/devices/{device}/test` | Send a test notification to one phone | yes |
| <span class="method get">GET</span> | `/api/apps` | The packages' apps and their state | yes |
| <span class="method post">POST</span> | `/api/apps/{package}/{action}` | Start, stop or restart an app's unit | yes |

## Webhooks

| Method | Route | What it does | Token |
|---|---|---|---|
| <span class="method post">POST</span> | `/hooks/wake/{trader}` | Wake a trader from TradingView or a script | webhook token |

## The event stream

`/ws/events?token=<token>` is a WebSocket that sends every event as JSON as it happens: its `kind`, its `trader`, its `payload` and its `created_at`. Add `&trader=intraday` to receive one trader's events and the events that belong to no trader, such as the kill switch. A wrong token closes the connection with code 1008. Changes to the roster arrive as events too: `trader_created` when a trader is created or restored, `trader_retired` when one is retired, and `trader_sleeping` when one falls asleep.

```json
{"kind": "tool_call", "trader": "general", "payload": {"trigger_id": "c38a67fb...", "call_id": "f60067d3...", "name": "get_portfolio", "arguments": {"kind": "funds"}}, "created_at": "2026-10-16T19:35:41.662832+00:00"}
```

Every other address that is not under `/api`, `/ws` or `/hooks` is answered with the web page.
