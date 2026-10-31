# Using it

There are four ways to reach the traders. The table below compares them.

| Way | Best for | Page |
|---|---|---|
| The web page at <http://127.0.0.1:8120> | Watching everything, editing your files, controlling traders and apps | [The web page](web-page.md) |
| The terminal program, `bin/trading-agent` | Everything the web page does, in a terminal, with Claude Code's keys | [The terminal program](terminal.md) |
| Telegram | Alerts and quick commands away from the computer | [Telegram](../telegram_setup.md) |
| The `trading-agent` subcommands and `-p` | Scripts, setup and checks | [Commands](commands.md) |

Talking to a trader works the same everywhere: a message becomes a turn, a slash command is answered by code, and a message sent while the trader is working steers the running turn. [Talking to a trader](chat.md) explains it. A trader can also ask you a question, show you a plan, or wait for your permission before certain actions, in the web chat, the terminal and on Telegram alike; [Questions, plans and permissions](questions-and-permissions.md) explains how.

<figure class="diagram">
--8<-- "docs/assets/diagrams/request-flow.svg"
<figcaption>The orange dot is a message going in through the gateway to a trader; the blue dot is every step of the trader's turn coming back as events, to the page and to every other listener such as the journal.</figcaption>
</figure>
