# Questions, plans and permissions

A trader works on its own, but sometimes a decision is genuinely yours: a detail missing from a strategy, a choice between two approaches, or an action you asked to be consulted about. Traders have three ways to involve you, borrowed from Claude Code. None of them makes the trader wait.

| Kind | Started by | What you see | What you can answer |
|---|---|---|---|
| A question | The trader, with `ask_user` | One to four multiple-choice questions, each with a short header and options with descriptions | Pick one option, or several when the question allows it, or type your own answer under **Other** |
| A plan | The trader, with `present_plan` | A plan written in Markdown | **Approve**, or **Keep planning** with what should change |
| A permission request | trading-agent itself, when a trader calls a tool listed in `[approvals]` | The exact call the trader wants to make | **Allow once**, **Always allow**, or **Deny** |

## The trader never waits

When a trader asks, the request is saved, the trader's turn ends, and the trader carries on with the rest of its work: its heartbeats, checks and fills keep arriving as usual. Your answer reaches it later as a new message that names the request. An unanswered request therefore holds nothing up, and a trader is never stuck waiting for you during market hours.

<figure class="diagram">
--8<-- "docs/assets/diagrams/user-requests.svg"
<figcaption>The orange dots are a request being saved and shown in the web chat and on Telegram. The blue dot is your answer, recorded once and handed to the trader as a new message. The expiry watcher tells the trader when a permission request lapses.</figcaption>
</figure>

## Where requests appear

In **Chat**, a waiting request is shown as a card docked above the message box, and a short summary of it stays in the conversation afterwards. A question card has one tab per question, a review step before you submit, and sometimes a preview beside the options.

In **the terminal program**, the same cards wait in a dock above the message box. Press Tab to answer and Esc to go back; the dock never takes the keyboard by itself, so a request that arrives while you type cannot receive your Enter. [The terminal program](terminal.md#questions-plans-and-permissions) explains why.

On **Telegram**, each request arrives as a message with buttons: one button per option, ticks and **Done** for a question that allows several answers, and a typed reply for **Other** and **Keep planning**. For a permission request you can also type `/approve` or `/deny`, as the [Telegram guide](../telegram_setup.md#6-try-it) explains.

A request answered in one place loses its buttons in the other, so it can never be answered twice. Every request also has a **Dismiss** button, which closes it without an answer.

## Permission prompts

A permission prompt is not something a trader chooses to ask for. The tools named in `[approvals]` in `trading_agent.toml` are held by trading-agent every time a trader or one of its subagents calls them, and the model has no way around that. This is the setting on this machine:

```toml
[approvals]
tools = [
    "flatten_trader",
]
expiry_minutes = 5
```

The steps below are what happens to a held call.

1. The trader calls `flatten_trader`. Instead of running, the call is saved as a permission request, and the trader is told to end its turn.
2. You see the exact call, with its arguments, in Chat and on Telegram.
3. If you allow it, trading-agent runs exactly that call, and it still passes through the risk engine like any other. If you deny it, the trader is told, with your reason if you gave one.
4. If nobody answers within `expiry_minutes`, the request lapses, the call is never run, and the trader is told. A lapse protects you from an action approved much later on prices that have moved.

**Always allow** lets that trader use that tool without asking until you revoke it. The standing permissions are listed on the **Settings** page, where each can be revoked.

Your own **Flatten** button on the Traders page is never held, because it is you acting rather than a trader.

!!! warning "Held calls and the scalper's 15:05 exit"
    The scalper's rules in TradingRules.md say it must be flat by 15:05 by calling `flatten_trader`. While `flatten_trader` is in `[approvals]`, that call waits for you and lapses after five minutes if nobody answers. Its bracket orders' stops and targets are held by UBI and are not affected. To let the scalper flatten itself, either choose **Always allow** for the scalper once, or remove `flatten_trader` from `[approvals]`.

## Where they are kept

Requests are saved per trader in `workspace/traders/<trader>/requests/`, and the standing permissions in `workspace/shared/permission_grants.json`. Both are working state, like the traders' notes, so git ignores them. The routes that read and answer them are listed in the [gateway API](../architecture/gateway-api.md#questions-plans-and-permissions).
