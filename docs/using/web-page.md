# The web page

The gateway serves the web page at <http://127.0.0.1:8120>. It asks once for the access token, the value of `TRADING_AGENT_GATEWAY_ACCESS_TOKEN` in `.env`, and keeps it in that browser. Its look is copied from Claude Code on the web: the colours, sizes and spacing were measured from Claude Code in both themes, and the page is shown 10% larger, as Chrome shows claude.ai, so the two look the same size side by side.

The header shows the trader that the trader-specific pages follow, chosen from a menu that also shows each trader's state. A sleeping trader is shown as "sleeping — wakes on the next message, alert, fill or heartbeat", and one held back by `[traders] maximum_running` as "waiting for a turn slot"; [The traders](../traders/index.md#what-a-trader-is-doing) explains every state. It also says whether orders are a **DRY RUN** or **LIVE ORDERS**, and whether the live connection is up. On the Chat page it has a button that shows or hides the side panel.

<figure class="diagram">
--8<-- "docs/assets/diagrams/web-page.svg"
<figcaption>The page loads once from the gateway. Orange dots are requests, each carrying the token; blue dots are the page and the live events coming back over one connection that every page shares.</figcaption>
</figure>

## The pages

The left sidebar groups the pages, and its foot has the theme switch and **Forget token**. The table below says what each page is for.

| Group | Page | What you can do there |
|---|---|---|
| Trade | **Traders** | One card per trader: state, mandate and schedule, today's profit or loss, halts, models in the order tried, the last thing it did; Chat, Pause or Resume, Flatten, and Retire. **New trader** creates a trader, and **Retired traders** lists the retired ones with **Restore**; [the section below](#creating-and-retiring-traders) describes them |
| | **Chat** | Talk to the chosen trader, answer its questions and permission requests, and follow its work; [the next section](#the-chat-page) describes it |
| | **Activity** | Every trader's events today, newest first, with a trader filter and search |
| | **Trading** | Balance, margin, today and this week, each trader's share and stocks, positions, halts, open orders, UBI's order book, and the kill switch |
| Memory | **Sessions** | Each day's conversation, the daily summaries, the notes, and a search of the trader's memory |
| | **Files** | Edit your files and each Memory.md; accept or reject the traders' proposals, shown as diffs |
| | **Checkpoints** | Every snapshot of a trader's own files, and restoring one |
| Automation | **Schedule** | Jobs with their next three runs, run now, delete, new jobs, the latest runs, price alerts |
| | **Skills** | Each skill, how often it was used, and how often it was followed by trouble |
| | **Extensions** | Subagents, MCP servers and installed packages |
| System | **Models** | Each trader's model order, today's token use and costs, including what DeepSeek charged, and Claude's subscription limits |
| | **Channels** | Telegram's state, codes waiting for approval, paired chats |
| | **Settings** | The configuration as the gateway read it, with secrets masked, and the standing "Always allow" permissions, each of which can be revoked |
| Apps | one entry per app | An installed package's web app, such as sridhara, with its state and Start, Restart and Stop |

## Creating and retiring traders

The **Traders** page is where you create, retire and restore traders while the gateway runs. The list below describes each control.

- **New trader** opens a form with the name, the mandate (what the trader trades and how), the models with the `[traders]` defaults ticked and tried in the order shown, the heartbeat in minutes (empty for the default, 0 for none) and the scheduled check times. The page checks the name and the times as you type, and shows the gateway's own reason if it refuses. **Create trader** creates and starts the trader, chooses it in the header and opens its chat, where its introduction arrives. The form says that the new trader may trade within the account-wide limits until it has limits of its own.
- **Retire** on a trader's card first asks for confirmation, explaining that the trader stops answering messages, running its schedule and receiving heartbeats, alerts and fills, while its files, memory and journal stay in its folder. A trader that still owns positions or has open orders is refused with "flatten it first". The button is hidden when only one trader is running, because the last one cannot be retired. If the retired trader was the one chosen in the header, the page switches to the first running trader.
- **Retired traders**, below the cards, lists every retired trader with **Restore**, which starts it again with its memory and sessions.

The list of traders refreshes at once when the gateway reports a `trader_created`, `trader_retired` or `trader_sleeping` event, so a change made from Telegram or the terminal shows up without reloading the page. [Creating a trader](../traders/index.md#creating-a-trader) describes the other ways to do the same.

## The chat page

The chat page has three parts: the conversation, the message box under it, and a side panel of cards on the right.

### The conversation

The trader's answers are drawn as formatted text, with headings, lists, tables, links and code blocks that have a Copy button. Your own messages stay plain, as in Claude Code. Raw HTML inside an answer is shown as text and never run, because traders read web pages and documents written by strangers.

While a turn runs, its last line shows what the trader is doing, as Claude Code does: a spinning orange spark, a few words such as "Fetching a quote · RELIANCE" or "Running a command", and the seconds so far. A finished turn keeps its total time. Several tool calls in a row fold into one summary line, such as "Fetched 2 quotes, ran a command (1 failed)", which opens to show each tool's card with its arguments and result. When a tool showed the model a picture, such as a screenshot, the picture appears under its card.

The chat stays at its newest line as it grows, unless you have scrolled up to read.

### The message box

The message box is one row of controls. The table below lists them from left to right.

| Control | What it does |
|---|---|
| Attach | Adds pictures or documents; dropping files on the box or pasting a picture also works, as [Pictures and documents](pictures-and-documents.md) explains |
| The text | Enter sends, Shift+Enter starts a new line, and `/` opens a menu of every [command](chat.md#slash-commands) and skill of the trader, read from the gateway |
| Stop | A circle with a square, shown only while the trader is working; it stops the running turn at once |
| Microphone | Fills the box as you speak, after any text already there |
| Send | An arrow, shown once there is something to send |

Below the box, a model menu lists the trader's models in the order they are tried, then submenus of Claude's and DeepSeek's other models, then **Auto**. Choosing a model makes the trader try it first from now on, as `/model` does. A different Claude model is switched inside the running conversation, so nothing is lost. A footer shows the trading mode.

A question, plan or permission request from the trader is docked above the message box until you answer it; [Questions, plans and permissions](questions-and-permissions.md) explains them.

!!! note "Where your voice goes"
    The microphone uses the browser's own speech recognition. In Chrome and Edge the audio is sent to Google's speech service, not through the gateway. Firefox has no speech recognition, so the button is disabled there.

### The side panel

The side panel on the right shows the chosen trader at a glance. Each card can be folded, and the whole panel can be hidden from the header; the page remembers both choices.

| Card | What it shows |
|---|---|
| Trader | Its state, its waiting triggers, its session, and whether orders are a dry run or live |
| Model | The model that answered last, the one you chose to try first, and the fallback order |
| Context | How much of the context window is used, with one row per category, such as messages or tool definitions |
| Funds | The account's balance and the margin in use |
| Profit and loss | This trader today, and the account today and this week |
| Orders and trades | Today's orders and fills of the trader |
| Tools | The trader's tools and its MCP servers' tools |
| Outputs | The files the trader sent you |

Claude's context numbers are measured by Claude Code at the end of each turn. The other models have no such report, so their breakdown is estimated from the conversation and marked "estimated". `/context` gives the same read-out on Telegram.

## On a phone

At up to 760 pixels wide the page switches to a layout modelled on the Claude Android app: a ☰ menu that slides in, the trader's name in the centre of the header, a rounded message box with the model chip beside **+**, and the side panel as a sheet that slides up. The same layout is what the [Android app](android-app.md) shows. On a phone, Enter adds a new line and the round button sends.

## Safety on the page

Risky buttons ask before acting. Flatten asks for a reason, which goes to the journal. Retire asks for confirmation and explains what stays. The kill switch asks for a reason and the typed word FLATTEN, and its button stays disabled until both are given. Saving a TradingRules.md that the risk engine cannot read is refused with the reason, so a typing mistake can never leave the traders without limits. Saving a Memory.md takes a checkpoint first, so the edit can be undone.

## Building it

The page lives in `frontend/` (React 19, TypeScript and Vite 8). Answers are drawn with react-markdown, remark-gfm and highlight.js. After changing the page, build it again:

```bash
source ~/.nvm/nvm.sh && cd frontend && npm run build
```

`npm run dev` starts a development server on port 5175 with hot reload, which passes `/api` and `/ws` through to the running gateway.
