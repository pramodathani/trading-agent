# Gateway API

The gateway listens on 127.0.0.1:8120. Every route under `/api` except `/api/health` needs the access token, sent as `Authorization: Bearer <token>`; a missing or wrong token gets 401. The web page uses exactly these routes, so anything it does can also be scripted.

```bash
TOKEN=$(grep ^TRADING_AGENT_GATEWAY_ACCESS_TOKEN .env | cut -d= -f2-)
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8120/api/desks
```

## Health

| Method | Route | What it does | Token |
|---|---|---|---|
| <span class="method get">GET</span> | `/api/health` | Is the gateway running, and each desk's state | no |

## Desks

| Method | Route | What it does | Token |
|---|---|---|---|
| <span class="method get">GET</span> | `/api/desks` | Every desk's state, models and session | yes |
| <span class="method get">GET</span> | `/api/desks/{desk}` | One desk, with its persona | yes |
| <span class="method post">POST</span> | `/api/desks/{desk}/messages` | Queue a message or slash command; the answer arrives as events | yes |
| <span class="method post">POST</span> | `/api/desks/{desk}/pause` | Stop the desk asking its models | yes |
| <span class="method post">POST</span> | `/api/desks/{desk}/resume` | Start it again | yes |
| <span class="method post">POST</span> | `/api/desks/{desk}/flatten` | Cancel the desk's orders and close its positions, with a reason | yes |

## The account

| Method | Route | What it does | Token |
|---|---|---|---|
| <span class="method get">GET</span> | `/api/account` | Balance, margin, day and week, each desk's profit, positions, owners, halts | yes |
| <span class="method get">GET</span> | `/api/orders` | UBI's order book: orders, trades or open parents | yes |
| <span class="method get">GET</span> | `/api/desk-orders` | Each desk's open orders in the desk order book | yes |
| <span class="method post">POST</span> | `/api/account/kill` | Fire the kill switch; needs {"confirm": "FLATTEN", "reason": ...} | yes |

## Memory and the journal

| Method | Route | What it does | Token |
|---|---|---|---|
| <span class="method get">GET</span> | `/api/desks/{desk}/sessions` | The desk's sessions | yes |
| <span class="method get">GET</span> | `/api/desks/{desk}/sessions/{session}` | One session's exchanges | yes |
| <span class="method get">GET</span> | `/api/desks/{desk}/summaries` | The daily summaries | yes |
| <span class="method get">GET</span> | `/api/desks/{desk}/notes` | The notes files | yes |
| <span class="method get">GET</span> | `/api/desks/{desk}/search` | Search the desk's memory | yes |
| <span class="method get">GET</span> | `/api/desks/{desk}/journal` | One day of the desk's journal | yes |
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
| <span class="method get">GET</span> | `/api/desks/{desk}/jobs` | The desk's jobs with their next runs, and the latest runs | yes |
| <span class="method post">POST</span> | `/api/desks/{desk}/jobs` | Create a job | yes |
| <span class="method delete">DELETE</span> | `/api/desks/{desk}/jobs/{job}` | Delete one of your jobs | yes |
| <span class="method post">POST</span> | `/api/desks/{desk}/jobs/{job}/run` | Start a job now | yes |
| <span class="method get">GET</span> | `/api/desks/{desk}/alerts` | The desk's price alerts | yes |
| <span class="method delete">DELETE</span> | `/api/desks/{desk}/alerts/{alert}` | Remove one | yes |

## Extensions and checkpoints

| Method | Route | What it does | Token |
|---|---|---|---|
| <span class="method get">GET</span> | `/api/desks/{desk}/skills` | The desk's skills with their usage | yes |
| <span class="method get">GET</span> | `/api/subagents` | The subagent definitions | yes |
| <span class="method get">GET</span> | `/api/mcp` | Each MCP server's state and tools | yes |
| <span class="method get">GET</span> | `/api/packages` | The installed packages | yes |
| <span class="method get">GET</span> | `/api/desks/{desk}/checkpoints` | The desk's checkpoints | yes |
| <span class="method post">POST</span> | `/api/desks/{desk}/checkpoints/{checkpoint}/restore` | Restore one | yes |

## System

| Method | Route | What it does | Token |
|---|---|---|---|
| <span class="method get">GET</span> | `/api/usage` | Today's tokens per desk and model, and Claude's limits | yes |
| <span class="method get">GET</span> | `/api/configuration` | The configuration, with secrets masked | yes |

## Channels and apps

| Method | Route | What it does | Token |
|---|---|---|---|
| <span class="method get">GET</span> | `/api/channels` | Telegram's state, waiting codes and paired chats | yes |
| <span class="method post">POST</span> | `/api/channels/telegram/pairings/{code}/approve` | Pair the chat that was given a code | yes |
| <span class="method delete">DELETE</span> | `/api/channels/telegram/chats/{chat}` | Unpair a chat | yes |
| <span class="method get">GET</span> | `/api/apps` | The packages' apps and their state | yes |
| <span class="method post">POST</span> | `/api/apps/{package}/{action}` | Start, stop or restart an app's unit | yes |

## Webhooks

| Method | Route | What it does | Token |
|---|---|---|---|
| <span class="method post">POST</span> | `/hooks/wake/{desk}` | Wake a desk from TradingView or a script | webhook token |

## The event stream

`/ws/events?token=<token>` is a WebSocket that sends every event as JSON as it happens: its `kind`, its `desk`, its `payload` and its `created_at`. Add `&desk=intraday` to receive one desk's events and the events that belong to no desk, such as the kill switch. A wrong token closes the connection with code 1008.

```json
{"kind": "tool_call", "desk": "main", "payload": {"trigger_id": "c38a67fb...", "call_id": "f60067d3...", "name": "get_portfolio", "arguments": {"kind": "funds"}}, "created_at": "2026-10-16T19:35:41.662832+00:00"}
```

Every other address that is not under `/api`, `/ws` or `/hooks` is answered with the web page.
