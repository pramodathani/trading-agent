# Security

trading-agent controls real money without a human approving its orders, runs a shell, browses the web and reads text written by strangers. The table below lists what protects each thing that matters, and where it is explained.

| What is protected | By what |
|---|---|
| The account | The risk engine's hard limits, read from your TradingRules.md, which no model can change; the kill switch at the daily loss limit; one stock per trader |
| Your instructions | Your files are read-only to the traders; they can only propose changes, which you accept |
| The machine | Each trader's bash runs in a bwrap sandbox that may write only its scratch folder, with credential folders and every `.env` hidden and an empty environment |
| The local network | The address guard: the browser and `web_fetch` reach only public internet addresses, checked again at each redirect |
| The gateway | Bound to 127.0.0.1; every API route except health needs the access token; the web page keeps the token in your browser only |
| Secrets | Masked in logs, journals, the live stream and the configuration page, including the Telegram bot token inside request addresses |
| The Claude subscription | `ANTHROPIC_API_KEY` is removed from Claude Code's environment, so the API is never billed by mistake; Claude Code's own tools are switched off and a hook allows only trading-agent's |
| Against planted instructions | Text from the web, MCP servers, the knowledge base and imported skills is labelled as untrusted data, and the files the traders read are scanned |
| The Android app | It reaches the gateway only over Tailscale, through `tailscale serve`, so the gateway still listens on 127.0.0.1; it signs in with the same access token, kept on the phone; the API answers cross-origin calls only from `[gateway] allowed_origins`, without cookies; debug builds alone may use plain HTTP, and only to `localhost` |
| Notifications | Phones register with the access token; the API never returns their Firebase tokens; the Firebase key lives outside the repository, readable only by you |
| Telegram | Only paired chats are obeyed; pairing needs a code approved on this machine, codes expire in an hour, and strangers are logged |
| Packages | Nothing a package brings runs inside the gateway; app controls are limited to the systemd units installed packages name, as your user, never as root |
| Actions you want to see first | The tools in `[approvals]` are held by trading-agent itself, not by the model, and run only as called, only if you allow them, and only within `expiry_minutes` |
| The web page against hostile text | A trader's answer is drawn as Markdown, and any raw HTML in it is shown as text and never run |
| Mistakes on the web page | Flatten needs a reason; the kill switch needs a reason and the word FLATTEN; a TradingRules.md the risk engine cannot read is never saved; Memory.md edits are checkpointed |

## What is deliberately not protected

The traders have network access from their shell, because they fetch market data and research. They can read the project's code and your files, because they need to understand their own tools and your instructions. They act without approval, because that is the purpose of the agent; the limits in TradingRules.md are where you decide how much they may risk, and `[approvals]` is where you choose actions to see first. Voice input in Chat uses the browser's speech recognition, so in Chrome your spoken words go to Google; the Android app uses the phone's speech recognizer, which on most phones is also Google's. The text of every app notification passes through Google's Firebase servers.
