# The web page

The gateway serves the web page at <http://127.0.0.1:8120>. It asks once for the access token, the value of `TRADING_AGENT_GATEWAY_ACCESS_TOKEN` in `.env`, and keeps it in that browser. Its look is copied from Claude Code on the web: the colours, sizes and spacing were measured from Claude Code in both themes, and the page is shown 10% larger, as Chrome shows claude.ai, so the two look the same size side by side.

The header shows the desk that the desk-specific pages follow, chosen from a menu that also shows each desk's state. It also says whether orders are a **DRY RUN** or **LIVE ORDERS**, and whether the live connection is up. On the Chat page it has a button that shows or hides the side panel.

<figure class="diagram">
--8<-- "docs/assets/diagrams/web-page.svg"
<figcaption>The page loads once from the gateway. Orange dots are requests, each carrying the token; blue dots are the page and the live events coming back over one connection that every page shares.</figcaption>
</figure>

## The pages

The left sidebar groups the pages, and its foot has the theme switch and **Forget token**. The table below says what each page is for.

| Group | Page | What you can do there |
|---|---|---|
| Trade | **Desks** | One card per desk: state, today's profit or loss, halts, models in the order tried, the last thing it did; Chat, Pause or Resume, and Flatten |
| | **Chat** | Talk to the chosen desk, answer its questions and permission requests, and follow its work; [the next section](#the-chat-page) describes it |
| | **Activity** | Every desk's events today, newest first, with a desk filter and search |
| | **Trading** | Balance, margin, today and this week, each desk's share and stocks, positions, halts, open orders, UBI's order book, and the kill switch |
| Memory | **Sessions** | Each day's conversation, the daily summaries, the notes, and a search of the desk's memory |
| | **Files** | Edit your files and each Memory.md; accept or reject the desks' proposals, shown as diffs |
| | **Checkpoints** | Every snapshot of a desk's own files, and restoring one |
| Automation | **Schedule** | Jobs with their next three runs, run now, delete, new jobs, the latest runs, price alerts |
| | **Skills** | Each skill, how often it was used, and how often it was followed by trouble |
| | **Extensions** | Subagents, MCP servers and installed packages |
| System | **Models** | Each desk's model order, today's token use and costs, including what DeepSeek charged, and Claude's subscription limits |
| | **Channels** | Telegram's state, codes waiting for approval, paired chats |
| | **Settings** | The configuration as the gateway read it, with secrets masked, and the standing "Always allow" permissions, each of which can be revoked |
| Apps | one entry per app | An installed package's web app, such as sridhara, with its state and Start, Restart and Stop |

## The chat page

The chat page has three parts: the conversation, the message box under it, and a side panel of cards on the right.

### The conversation

The desk's answers are drawn as formatted text, with headings, lists, tables, links and code blocks that have a Copy button. Your own messages stay plain, as in Claude Code. Raw HTML inside an answer is shown as text and never run, because desks read web pages and documents written by strangers.

While a turn runs, its last line shows what the desk is doing, as Claude Code does: a spinning orange spark, a few words such as "Fetching a quote · RELIANCE" or "Running a command", and the seconds so far. A finished turn keeps its total time. Several tool calls in a row fold into one summary line, such as "Fetched 2 quotes, ran a command (1 failed)", which opens to show each tool's card with its arguments and result. When a tool showed the model a picture, such as a screenshot, the picture appears under its card.

The chat stays at its newest line as it grows, unless you have scrolled up to read.

### The message box

The message box is one row of controls. The table below lists them from left to right.

| Control | What it does |
|---|---|
| Attach | Adds pictures or documents; dropping files on the box or pasting a picture also works, as [Pictures and documents](pictures-and-documents.md) explains |
| The text | Enter sends, Shift+Enter starts a new line, and `/` starts a [command](chat.md#slash-commands) |
| Stop | A circle with a square, shown only while the desk is working; it stops the running turn at once |
| Microphone | Fills the box as you speak, after any text already there |
| Send | An arrow, shown once there is something to send |

Below the box, a model menu lists the desk's models in the order they are tried, then submenus of Claude's and DeepSeek's other models, then **Auto**. Choosing a model makes the desk try it first from now on, as `/model` does. A different Claude model is switched inside the running conversation, so nothing is lost. A footer shows the trading mode.

A question, plan or permission request from the desk is docked above the message box until you answer it; [Questions, plans and permissions](questions-and-permissions.md) explains them.

!!! note "Where your voice goes"
    The microphone uses the browser's own speech recognition. In Chrome and Edge the audio is sent to Google's speech service, not through the gateway. Firefox has no speech recognition, so the button is disabled there.

### The side panel

The side panel on the right shows the chosen desk at a glance. Each card can be folded, and the whole panel can be hidden from the header; the page remembers both choices.

| Card | What it shows |
|---|---|
| Desk | Its state, its waiting triggers, its session, and whether orders are a dry run or live |
| Model | The model that answered last, the one you chose to try first, and the fallback order |
| Context | How much of the context window is used, with one row per category, such as messages or tool definitions |
| Funds | The account's balance and the margin in use |
| Profit and loss | This desk today, and the account today and this week |
| Orders and trades | Today's orders and fills of the desk |
| Tools | The desk's tools and its MCP servers' tools |
| Outputs | The files the desk sent you |

Claude's context numbers are measured by Claude Code at the end of each turn. The other models have no such report, so their breakdown is estimated from the conversation and marked "estimated". `/context` gives the same read-out on Telegram.

## Safety on the page

Risky buttons ask before acting. Flatten asks for a reason, which goes to the journal. The kill switch asks for a reason and the typed word FLATTEN, and its button stays disabled until both are given. Saving a TradingRules.md that the risk engine cannot read is refused with the reason, so a typing mistake can never leave the desks without limits. Saving a Memory.md takes a checkpoint first, so the edit can be undone.

## Building it

The page lives in `frontend/` (React 19, TypeScript and Vite 8). Answers are drawn with react-markdown, remark-gfm and highlight.js. After changing the page, build it again:

```bash
source ~/.nvm/nvm.sh && cd frontend && npm run build
```

`npm run dev` starts a development server on port 5175 with hot reload, which passes `/api` and `/ws` through to the running gateway.
