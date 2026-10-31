# The Android app

Trading Agent for Android puts the web page on your phone, laid out like the Claude Android app, with the phone's own speech recognition for the microphone and notifications that arrive even when the app is closed. It is a [Capacitor](https://capacitorjs.com) app: a small Android shell around its own copy of the built web page, so every page, card and button is the same code as on the desktop.

The app talks to the gateway on this computer over [Tailscale](https://tailscale.com), a private network between your own devices. The gateway keeps listening on 127.0.0.1 only; `tailscale serve` gives it an HTTPS address that only your devices can reach, wherever the phone is.

<figure class="diagram">
--8<-- "docs/assets/diagrams/android-app.svg"
<figcaption>The orange dot is a call from the app, which travels over Tailscale to <code>tailscale serve</code> and on to the gateway. The blue dots are what comes back: answers and live events the same way, and notifications through Firebase Cloud Messaging, which can wake the phone when the app is closed.</figcaption>
</figure>

## What the app looks like

At up to 760 pixels wide, the web page switches to a phone layout, so the same layout also appears in a phone's browser.

| Part | On the phone |
|---|---|
| Header | ☰ on the left, the trader's name in the centre (tap it to switch traders), a short **DRY** or **LIVE** badge, the connection dot, and the details button |
| ☰ menu | A drawer that slides in from the left with every page, the theme switch and **Forget token** |
| Chat | Your messages on the right in bubbles, the trader's answers full width, as in the Claude app |
| Message box | A rounded card at the bottom: the text on top, then **+** to attach, the model chip, the microphone and a round send button. Enter adds a new line; the send button sends |
| Details | The side panel's cards (trader, model, context, funds, profit and loss, orders, tools, outputs) slide up as a sheet from the bottom |
| Back button | Closes the drawer or the sheet first, then goes back a page; from the chat it puts the app in the background |
| Files and links | A document or picture from a trader opens in the phone's viewer for its type; a link opens in an in-app browser sheet |

The app opens on the chat. The microphone uses Android's speech recognizer, which on most phones is Google's speech service: the words appear in the box as you speak, and listening stops when you pause or tap the microphone again. Android asks for the microphone the first time.

## Setting it up

### 1. Tailscale

1. Install Tailscale on this computer and sign in:

    ```bash
    curl -fsSL https://tailscale.com/install.sh | sh
    sudo tailscale up
    ```

2. Install **Tailscale** from the Play Store on the phone and sign in with the same account.
3. In the Tailscale admin console, on the **DNS** page, turn on **MagicDNS** and **HTTPS Certificates**.
4. Publish the gateway to your devices, in the background so it survives restarts:

    ```bash
    sudo tailscale serve --bg 8120
    tailscale serve status
    ```

    The status shows the address, such as `https://desktop.tail1234.ts.net`. It is reachable only from devices signed in to your Tailscale account.

### 2. Firebase, for notifications

Notifications go through Google's Firebase Cloud Messaging, because only Google's servers can wake an Android app that is closed.

1. At [console.firebase.google.com](https://console.firebase.google.com), create a project (Analytics can stay off).
2. Add an Android app with the package name `com.pramodathani.tradingagent`, download `google-services.json`, and put it in `frontend/android/app/`. Git ignores it.
3. Under **Project settings → Service accounts**, generate a private key. Keep that file outside the repository, readable only by you, and name it in `.env`:

    ```bash
    TRADING_AGENT_FIREBASE_SERVICE_ACCOUNT_FILE=/home/pramod/.config/trading-agent/firebase-service-account.json
    ```

4. Switch push on in `trading_agent.toml` and restart the gateway:

    ```toml
    [push]
    enabled = true
    ```

### 3. Build and install the app

The app is built on this computer and installed over USB. It needs Java 21 at `~/.local/opt/jdk-21` and the Android SDK at `~/Android/Sdk`, with the platform tools, `platforms;android-36` and `build-tools;36.0.0`.

1. On the phone, open **Settings → About phone** (on Samsung, **Software information**), tap **Build number** seven times, then turn on **Developer options → USB debugging**.
2. Connect the phone with a data cable and tap **Allow** when it asks to allow USB debugging.
3. Build and install in one step:

    ```bash
    source ~/.nvm/nvm.sh && cd frontend && npm run android
    ```

    `npm run android` builds the web page, copies it into the Android project (`cap sync`), builds the debug app with Gradle and installs it with `adb install -r`. The app carries its own copy of the page, so a change to the page, such as the **New trader** form and the **Retire** buttons added on 31 October 2026, reaches the phone only after this command is run again. The same work is also available in three parts: `android:sync` (build and copy the page), `android:build` (the app) and `android:install`.

Run it again after any change to the web page, because the app carries its own copy of the page.

### 4. Sign in

Open **Trading Agent** on the phone. The first page asks for the gateway's Tailscale address and the access token, the value of `TRADING_AGENT_GATEWAY_ACCESS_TOKEN` in `.env`; both are kept on the phone. After signing in, the app asks to show notifications and registers the phone with the gateway.

## Notifications

`[push] notifications` chooses what is pushed. The names are Telegram's, without daily summaries, plus `requests`:

| Name | What is pushed |
|---|---|
| `fills` | A broker order finished, with the quantity and price |
| `rejections` | The risk engine refused an order, with its reasons |
| `model_switches` | A trader moved to another model |
| `job_results` | A scheduled job finished |
| `trader_reports` | What a trader said when it woke on its own, such as at a scheduled check |
| `messages` | A trader's `send_message`, marked when urgent |
| `alerts` | A price alert fired |
| `halts` | A trader was halted, or the kill switch fired |
| `errors` | A turn failed |
| `requests` | A trader asks a question or presents a plan, or an action waits for your permission |

Each notification is titled with its trader, and tapping it opens that trader's chat. A permission request lapses after `[approvals] expiry_minutes`, so its notification is the one to act on quickly.

**Settings → Phones** lists the registered phones, each with **Send test** and **Remove**. A phone that uninstalls the app is removed by itself the next time Firebase reports its token as gone.

The text of every notification passes through Google's servers on its way to the phone.

## Testing over USB without Tailscale

A test gateway on this computer can be reached from the phone through the USB cable. `adb reverse` makes the phone's `localhost:8121` lead to port 8121 here:

```bash
~/Android/Sdk/platform-tools/adb reverse tcp:8121 tcp:8121
```

Sign in to `http://localhost:8121`. Android normally refuses plain `http://`, so debug builds alone allow it for `localhost` (`frontend/android/app/src/debug/`); release builds keep the block. Reinstalling the app drops the `adb reverse` rule, so set it again after each install.

The app's WebView can be inspected from Chrome on this computer at `chrome://inspect`, because debug builds allow it.
