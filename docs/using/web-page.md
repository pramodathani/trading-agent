# The web page

The gateway serves the web page at <http://127.0.0.1:8120>. It asks once for the access token, the value of `TRADING_AGENT_GATEWAY_ACCESS_TOKEN` in `.env`, and keeps it in that browser. The header shows the desk the desk-specific pages follow, whether orders are a **DRY RUN** or **LIVE ORDERS**, and whether the live connection is up.

<figure class="diagram">
--8<-- "docs/assets/diagrams/web-page.svg"
<figcaption>The page loads once from the gateway. Orange dots are requests, each carrying the token; blue dots are the page and the live events coming back over one connection that every page shares.</figcaption>
</figure>

## The pages

The sidebar groups the pages. The table below says what each one is for.

| Group | Page | What you can do there |
|---|---|---|
| Trade | **Desks** | One card per desk: state, today's profit or loss, halts, models in the order tried, the last thing it did; Chat, Pause or Resume, and Flatten |
| | **Chat** | Talk to the chosen desk; see each turn's tool calls, the text as it is written, and a Stop button |
| | **Activity** | Every desk's events today, newest first, with a desk filter and search |
| | **Trading** | Balance, margin, today and this week, each desk's share and stocks, positions, halts, open orders, UBI's order book, and the kill switch |
| Memory | **Sessions** | Each day's conversation, the daily summaries, the notes, and a search of the desk's memory |
| | **Files** | Edit your files and each Memory.md; accept or reject the desks' proposals, shown as diffs |
| | **Checkpoints** | Every snapshot of a desk's own files, and restoring one |
| Automation | **Schedule** | Jobs with their next three runs, run now, delete, new jobs, the latest runs, price alerts |
| | **Skills** | Each skill, how often it was used, and how often it was followed by trouble |
| | **Extensions** | Subagents, MCP servers and installed packages |
| System | **Models** | Each desk's model order, today's token use, Claude's subscription limits |
| | **Channels** | Telegram's state, codes waiting for approval, paired chats |
| | **Settings** | The configuration as the gateway read it, with secrets masked |
| Apps | one entry per app | An installed package's web app, such as sridhara, with its state and Start, Restart and Stop |

## Safety on the page

Risky buttons ask before acting. Flatten asks for a reason, which goes to the journal. The kill switch asks for a reason and the typed word FLATTEN, and its button stays disabled until both are given. Saving a TradingRules.md that the risk engine cannot read is refused with the reason, so a typing mistake can never leave the desks without limits. Saving a Memory.md takes a checkpoint first, so the edit can be undone.

## Building it

The page lives in `frontend/` (React 19, TypeScript and Vite 8). After changing it:

```bash
source ~/.nvm/nvm.sh && cd frontend && npm run build
```

`npm run dev` starts a development server on port 5175 with hot reload, which passes `/api` and `/ws` through to the running gateway.
