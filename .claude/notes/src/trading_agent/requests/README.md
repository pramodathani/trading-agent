# requests/

The desks' questions, plans and permission requests to the user, built on 2026-10-18 to copy Claude Code's AskUserQuestion card, plan approval and permission prompt.

Decisions the user made:

- A desk never waits for an answer. The request is saved, the turn ends, and the answer arrives as a new user message carrying `request_id`, so the desk keeps reacting to the market and an unanswered question costs nothing.
- Requests are shown in the web chat and, with buttons, on Telegram. Whichever answers first wins; the other loses its buttons.
- Only `flatten_desk` needs permission (`[approvals] tools` in trading_agent.toml), permission requests lapse after 5 minutes, and "Always allow" lasts until revoked on the Settings page.

Why permissions are enforced in the tool-call executor, not by a tool the desk calls: a desk that could choose whether to ask could choose not to. The executor holds the call for desks and subagents alike; the user's own Flatten button calls the desk's tool registry directly and is not held. When allowed, the responder runs exactly the held call through the desk's registry, so the risk engine still checks it.

Why a lapsed request is saved only by `expire_lapsed`: listing requests shows lapsed ones as expired without saving them, so the expiry watcher is the only place that saves the change and tells the desk, exactly once.

The answer texts call the person "the user" rather than a name, because User.md is the place that names them.
