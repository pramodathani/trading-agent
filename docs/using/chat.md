# Talking to a desk

A message to a desk becomes a **turn**: the desk reads it with its instructions, thinks, calls tools, and answers. Every step is shown as it happens. In Chat a tool call is a folded card with its arguments and result, and the answer appears as it is written. Messages can carry pictures and documents, both ways; [Pictures and documents](pictures-and-documents.md) explains how.

## Slash commands

A message that starts with a slash is a command. They work in Chat, on Telegram and with `bin/trading-agent send`. Most are answered by code without asking a model; `/btw` and `/review` ask one, and say so. Several of them were borrowed from Claude Code, OpenClaw and Hermes Agent, which use the same names.

The last column says when a command is answered. **At once** means it is answered straight away, even while the desk is in the middle of a turn. **Beside** means it runs next to the turn, without waiting for it or interrupting it, and only one such command runs on a desk at a time. **Queued** means it waits until the running turn has finished, because it changes the desk.

| Command | What it does | When |
|---|---|---|
| `/status` | What the desk is doing and which models are ready | At once |
| `/usage` | Today's model calls, tokens, costs and Claude's limits | At once |
| `/context` | How full the context window is, and what fills it | At once |
| `/tools`, `/tools full` | The tools the desk can call, with the first sentence or the whole of each description | At once |
| `/skills` | Your skills and the ones the desk wrote, plus skills that cannot be used here and why | At once |
| `/subagents` | The desk's subagents, and today's runs with their outcome | At once |
| `/help` | The list | At once |
| `/stop` | Stops the running turn | At once |
| `/btw <question>` | A side question, such as `/btw why did you sell INFY?`, answered from the desk's conversation; neither the question nor the answer is kept in it | Beside |
| `/review [notes]` | The trade reviewer subagent judges today's orders and fills against your rules, with any notes you add | Beside |
| `/model` | Shows the model order; `/model qwen` tries that model first from now on; `/model auto` goes back to the configured order | Queued |
| `/think` | Shows how hard each model thinks; `/think off`, `low`, `medium`, `high`, `xhigh` or `max` sets it from the next turn; `/think default` goes back to the configuration | Queued |
| `/new` | Forgets this conversation and starts a fresh one | Queued |
| `/compact` | Saves what matters, then compresses the conversation into a summary | Queued |
| `/rollover` | Summarises the day and starts a fresh session now | Queued |
| `/pause`, `/resume` | Stops the desk asking any model, and starts it again; commands still work while paused, except `/btw` and `/review`, which ask a model | Queued |
| `/<skill-name> ...` | Asks the desk to follow one of its skills | Queued |

`/model` and `/think` last until the gateway restarts; lasting settings belong in `trading_agent.toml`. For Claude, a new `/think` level restarts Claude Code at the next turn and resumes the same session, so the conversation is kept. Qwen and Gemma think or not, so every level except `off` turns thinking on. DeepSeek and OpenAI decide for themselves.

`/btw` asks the model that answered last. For Claude it runs in a throwaway copy of the session, in which every tool call is refused, and the copy is deleted afterwards.

On Telegram, a few commands are answered by the channel itself and cover every desk: `/status`, `/positions`, `/pnl`, `/desk`, `/pause all`, `/resume all`, `/approve`, `/deny` and `/kill CONFIRM <reason>`. The [Telegram guide](../telegram_setup.md#6-try-it) lists them. Typing `/` on the phone shows a menu of all the commands.

## Steering a turn

A long turn can take minutes. A message you send while the desk is working does not wait for the turn to end: it goes to the desk's **steering inbox**, and the running turn picks it up at its next tool call. If the turn ends without another tool call, the message becomes the next turn, so nothing you write is lost. Chat shows the message inside the running turn, with whether it was handed over.

<figure class="diagram">
--8<-- "docs/assets/diagrams/steering.svg"
<figcaption>The orange dots are your message going into the steering inbox, and /stop skipping the queue; the blue dot is the message being handed to the running turn at its next tool round.</figcaption>
</figure>

For Qwen and Gemma, the agent loop adds the message to the conversation before its next model call. For Claude, a `PostToolUse` hook hands it over after each tool call. Slash commands are never steering. The ones marked "At once" or "Beside" above are answered without waiting for the turn, and the rest wait in the queue.

## Stopping a turn

`/stop`, or the Stop button in Chat, cancels the running turn at once. Tools that already ran are not undone: an order already placed stays placed. The turn answers "Stopped by the user", and the desk is ready for the next message.

On 17 October 2026, Qwen was asked to call `get_time` four times, and while it worked it was told to end its answer with the word BANANA; it did. A 700-word essay was then stopped mid-sentence, and the next message was answered normally.
