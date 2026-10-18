# Setting up Telegram

This guide connects trading-agent to Telegram, so you can talk to the desks from your phone and get notified when an order fills, a desk is halted or a desk reports something at a scheduled check. It assumes you have never used Telegram before. It takes about fifteen minutes.

## How it works, in one paragraph

Telegram lets anyone create a *bot*: an account that a program, rather than a person, sends messages from. You create a bot for trading-agent with Telegram's own bot-making account, called BotFather, and BotFather gives you a *token*, which is the bot's password. trading-agent uses the token to read the messages you send the bot and to answer them. It asks Telegram for new messages every few seconds, so your computer needs no open port and no public address. Because anyone in the world can find a bot and message it, the bot obeys only the chats you *pair* by approving a code on your computer.

## 1. Install Telegram and create an account

1. On your phone, install **Telegram** from the Play Store (Android) or the App Store (iPhone). The publisher is Telegram FZ-LLC.
2. Open it, tap **Start Messaging**, and enter your phone number. Telegram sends a code by SMS or as a Telegram message; type it in.
3. Enter a first name. A last name and a photo are optional.

You can also use Telegram on this computer at <https://web.telegram.org>, signing in with the same phone number, but the phone is enough.

## 2. Create the bot with BotFather

1. In Telegram, tap the search icon and type `BotFather`. Open the account named **BotFather** with the username **@BotFather** and a blue tick next to the name. Other accounts with similar names are imitations; ignore them.
2. Tap **Start**.
3. Send `/newbot`.
4. BotFather asks for a **name**. This is what you see at the top of the chat, and it can be anything, such as `Pramod's trading agent`.
5. BotFather asks for a **username**. It must be unique across Telegram and end in `bot`, such as `pramod_trading_agent_bot`. If it is taken, try another.
6. BotFather replies with a message that contains the **token**, a long line such as `123456789:AAH...`. Keep this message private.

The token is the bot's password. Anyone who has it can read what you send the bot and send messages that look like they come from it. They still could not command the desks, because pairing stops that, but treat the token like a password all the same: do not paste it into a chat, an email, or a conversation with Claude.

### Recommended BotFather settings

Still in the BotFather chat:

Send `/setjoingroups`, choose your bot, and choose **Disable**. The bot then cannot be added to group chats, where other people could see its messages.

You do not need BotFather's `/setcommands`. Each time the gateway connects, it registers the bot's command menu itself, so the menu always matches the commands trading-agent has. `/kill` is left out of the menu on purpose, so it cannot be tapped by mistake.

## 3. Give the token to trading-agent

1. On this computer, open the project's `.env` file in a text editor, for example:

   ```bash
   nano /home/pramod/Projects/trading-agent/.env
   ```

2. Add this line, with your token after the `=` and no spaces or quotes:

   ```text
   TRADING_AGENT_TELEGRAM_BOT_TOKEN=123456789:AAH...
   ```

3. Save and close the file (in nano: Ctrl+O, Enter, Ctrl+X).

`.env` is never committed to git, and the gateway masks the token in its logs, journal and web page.

## 4. Switch Telegram on

1. Open `trading_agent.toml` and find the `[telegram]` section near the end:

   ```toml
   [telegram]
   enabled = true
   default_desk = "general"
   ```

   Set `enabled = true`. `default_desk` is the desk a new chat talks to.

2. Check the setup:

   ```bash
   bin/trading-agent doctor
   ```

   The Telegram line should say that Telegram knows the bot as `@your_bot_username`. If it says the token was refused, copy the token again from BotFather.

3. Restart the gateway: `systemctl --user restart trading-agent`.

## 5. Pair your phone

1. On your phone, search Telegram for your bot's username, or open `https://t.me/your_bot_username`, and tap **Start**.
2. The bot replies with an eight-letter code, such as `K7MQ2XPA`, and the bot will obey nothing else from your chat until you approve it.
3. On this computer, approve the code in either of two ways:
   - In the web page (<http://127.0.0.1:8120>), open **Channels**. Your code is listed under "Waiting for approval" with your name; press **Approve**.
   - Or in a terminal:

     ```bash
     bin/trading-agent pairing approve K7MQ2XPA
     ```

4. If you approved in the web page, the bot answers "Paired" at once. After the terminal command, send the bot any message; it now obeys you. A code expires after an hour; if yours did, send the bot any message to get a new one.

## 6. Try it

Send these to the bot:

| Send | What happens |
|---|---|
| `/status` | Every desk's state and the account's balance and day, answered by code without a model, so it works even when every model is down |
| `/pnl` | Today's and this week's profit or loss, and each desk's share |
| `/positions` | Open positions and which desk owns each |
| `What is your plan for Monday?` | The message goes to your desk (general at first), and its answer comes back |
| `/desk intraday` | Later messages go to the intraday desk |
| `/pause all` | Every desk stops asking its models; `/resume all` starts them again |
| `/stop` | The desk's running turn stops at once |
| `/btw why did you sell INFY?` | A side answer from the desk, which is not kept in its conversation |
| `/context` | How full the desk's context window is |
| `/approve` or `/deny <reason>` | Allows or refuses an action a desk is holding for your permission, the same as its buttons. With several waiting, the bot lists them and you add the six-character id, as in `/approve a1b2c3`; `/approve a1b2c3 always` allows it from now on |
| `/kill CONFIRM <reason>` | Every desk is halted until tomorrow and the whole account is flattened. Without the word CONFIRM, nothing happens |

Typing `/` shows a menu of every command, and `/help` lists them. The desk's own commands, such as `/usage`, `/model`, `/think`, `/review` and `/tools`, are passed to your desk; [Talking to a desk](using/chat.md#slash-commands) describes them all.

A message you send while the desk is working is handed to the running turn at its next tool call, as on the web page; the bot tells you so.

When a desk asks you a question, shows you a plan or wants permission for an action, the bot sends it with buttons: one per option, ticks and **Done** when several answers are allowed, **Approve** and **Keep planning** for a plan, and **Allow once**, **Always allow** and **Deny** for a permission request. **Other** and **Keep planning** ask you to type a reply, and your next message is taken as that reply rather than sent to the desk. [Questions, plans and permissions](using/questions-and-permissions.md) explains them.

## 7. Choose what is pushed to you

Without being asked, the bot sends every paired chat the events listed in `notifications` under `[telegram]`. By default that is all of them:

| Name | What you get |
|---|---|
| `fills` | An order of a desk was filled, rejected or cancelled at the broker |
| `rejections` | The risk engine refused an order |
| `model_switches` | A desk switched model because one failed or hit a limit |
| `job_results` | A command job finished |
| `desk_reports` | What a desk said when it woke on its own: a scheduled check, a heartbeat that found something to do, a price alert or a webhook |
| `messages` | A desk used `send_message` to tell you something, or `send_image` to show you a picture while no chat was waiting for its answer |
| `alerts` | A price alert fired |
| `halts` | A desk reached its loss limit, or the kill switch fired |
| `errors` | A turn failed |
| `daily_summaries` | Each desk's summary of the day, after the close |

To get fewer, list only the ones you want, for example:

```toml
notifications = ["fills", "halts", "messages", "daily_summaries"]
```

and restart the gateway.

## If something goes wrong

| Problem | What to do |
|---|---|
| The bot does not answer at all | Run `bin/trading-agent doctor`; check the gateway is running and the Channels page says Connected |
| The Channels page says "Cannot reach Telegram" | Check the internet connection; the gateway keeps retrying by itself |
| The log says `Conflict: terminated by other getUpdates request` | Two gateways are using the same token; stop one |
| You lost your phone | Unpair it on the Channels page, or run `bin/trading-agent pairing list` and then `bin/trading-agent pairing revoke <chat id>` |
| The token may have leaked | In BotFather send `/revoke`, choose the bot, put the new token in `.env`, and restart. The old token stops working at once |
| Someone else messaged the bot | They got a code and nothing else. Their message is logged on the Activity page; do not approve their code |
