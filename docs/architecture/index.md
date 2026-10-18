# Architecture

trading-agent is one long-running process, the **gateway**. It owns every desk, serves the web page and the API, and runs the background loops that wake the desks. Nothing a package brings runs inside it: MCP servers, hooks and apps are separate programs.

## The parts

| Part | Its job |
|---|---|
| Desk runtime | One per desk: its queue of triggers, its turn runner, its steering inbox and its commands |
| Turn runners | The agent loop for Qwen, Gemma, DeepSeek and OpenAI-compatible servers; the Claude Code runner for Claude |
| Model router | One per desk: tries its models in order and falls back |
| Prompt builder | Turns your files, the desk's memory and the skills index into the instructions |
| Tool registry | The 49 tools, as schemas for the other models and as an in-process MCP server for Claude |
| Tool-call executor and permission gate | Runs each tool call, publishes it, and holds the calls listed in `[approvals]` until you allow them |
| Request store and responder | Keeps the desks' questions, plans and permission requests, and hands your answers back as new messages |
| Attachment store | Keeps the pictures and documents sent to or by each desk |
| Risk engine and ledger | Judges every order; records who owns which stock, halts and daily results |
| Event bus | Carries every step of every turn to everything that listens |
| Trade journal | Writes every event, masked, one file per desk per day |
| Cron scheduler | Wakes the desks on the clock, on trading days |
| Market watcher | Reads fills, prices and the account, and fires the kill switch |
| Telegram channel | Talks to paired phones |
| Gateway API | The HTTP routes and the event stream, behind the access token |

<figure class="diagram">
--8<-- "docs/assets/diagrams/gateway-api.svg"
<figcaption>Requests from the web page or a script reach each desk's parts and the shared parts through seven route groups. The orange dot to UBI is the kill switch; the blue dots are answers and live events.</figcaption>
</figure>

## The event bus

Every step of every turn is an event: a trigger received, a turn started, a tool called and its result, a model's usage, a model switch, a risk decision, an order, a fill, a text answer, a turn finished, and more. Each event names its desk. The journal, the usage tracker, the skill usage tracker, the hook runner, the Telegram channel and every open web page listen to the same bus, so adding a listener never changes a desk.

## The pages in this section

| Page | What it covers |
|---|---|
| [Gateway API](gateway-api.md) | Every HTTP route and the event stream |
| [Security](security.md) | What protects the account, the secrets and the machine |
| [Design choices](design-choices.md) | Why it is built the way it is |
