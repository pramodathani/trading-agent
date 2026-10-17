# Talking to a desk

A message to a desk becomes a **turn**: the desk reads it with its instructions, thinks, calls tools, and answers. Every step is shown as it happens. In Chat a tool call is a folded card with its arguments and result, and the answer appears as it is written.

## Slash commands

A message that starts with a slash is a command, answered by code without asking a model. They work in Chat, on Telegram and with `bin/trading-agent send`.

| Command | What it does |
|---|---|
| `/status` | What the desk is doing and which models are ready |
| `/model` | Shows the model order; `/model qwen` tries that model first from now on; `/model auto` goes back to the configured order |
| `/new` | Forgets this conversation and starts a fresh one |
| `/compact` | Saves what matters, then compresses the conversation into a summary |
| `/rollover` | Summarises the day and starts a fresh session now |
| `/usage` | Today's model calls, tokens, costs and Claude's limits |
| `/stop` | Stops the running turn at once |
| `/pause`, `/resume` | Stops the desk asking any model, and starts it again; commands still work while paused |
| `/<skill-name> ...` | Asks the desk to follow one of its skills |
| `/help` | The list |

On Telegram, a few commands are answered by the channel itself and cover every desk: `/status`, `/positions`, `/pnl`, `/desk`, `/pause all`, `/resume all` and `/kill CONFIRM <reason>`. The [Telegram guide](../telegram_setup.md#6-try-it) lists them.

## Steering a turn

A long turn can take minutes. A message you send while the desk is working does not wait for the turn to end: it goes to the desk's **steering inbox**, and the running turn picks it up at its next tool call. If the turn ends without another tool call, the message becomes the next turn, so nothing you write is lost. Chat shows the message inside the running turn, with whether it was handed over.

<figure class="diagram">
--8<-- "docs/assets/diagrams/steering.svg"
<figcaption>The orange dots are your message going into the steering inbox, and /stop skipping the queue; the blue dot is the message being handed to the running turn at its next tool round.</figcaption>
</figure>

For Qwen and Gemma, the agent loop adds the message to the conversation before its next model call. For Claude, a `PostToolUse` hook hands it over after each tool call. Slash commands are never steering: they wait in the queue, except `/stop`.

## Stopping a turn

`/stop`, or the Stop button in Chat, cancels the running turn at once. Tools that already ran are not undone: an order already placed stays placed. The turn answers "Stopped by the user", and the desk is ready for the next message.

On 17 October 2026, Qwen was asked to call `get_time` four times, and while it worked it was told to end its answer with the word BANANA; it did. A 700-word essay was then stopped mid-sentence, and the next message was answered normally.
