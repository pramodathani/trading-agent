# slash_commands.py

Commands are answered by code, never by a model, so they cost nothing, work while every model is down, and cannot be misread. They are dispatched through an explicit dictionary from command name to method, rather than looking methods up by name with `getattr`, following the user's preference for plain code.

`/model <name>` puts one backend first while keeping the others behind it, so the desk still falls back when that backend fails; `/model auto` returns to the configured order. `/new` resets every backend's conversation and the router's hand-over history. `/pause` stops the desk from asking any model while commands keep working, which is the quickest way to stop a desk without stopping the gateway.

Commands that belong to later milestones (`/compact`, `/usage`, `/think`, `/stop`) answer with the milestone they arrive in, rather than "unknown command".

## Sessions (milestone 11)

`/status` shows the session id and how many exchanges it has, and `/new` names the new session it started. `/new` does not write a summary of the session it ends; only the daily rollover does.

## /compact (milestone 12)

`/compact` is now real: it builds a trigger for event tagging and calls the router's `compact`. The test of not-yet-built commands now uses `/usage`.

## /<skill-name> (milestone 13)

`skill_request` turns `/breakout NIFTY` into a model turn asking the desk to load and follow that skill, with the rest of the line as its input. Built-in commands win over a skill of the same name, so a skill called `status` can never take over `/status`.

## /rollover (milestone 15)

Summarises the day and starts a fresh session now; the built-in after-close job sends it at 15:45 on trading days.

## /usage (milestone 15)

Shows the usage tracker's summary for the desk. The test of not-yet-built commands now uses /think.

## /stop (milestone 18)

/stop is no longer a "later" command. It is handled by the desk runtime before the queue, because a command that waits its turn cannot stop the turn in front of it. /help lists it.

## Command words and instant commands, since 2026-10-18

`command_name` takes the first word, drops a `@botname` suffix and lowercases it. Telegram adds the suffix when a command is picked from the menu in a group chat; before this, `/usage@my_bot` reached the desk and was answered "Unknown command". `_argument` splits on any whitespace, so an argument on the next line also works.

`is_instant` names the commands that only read the desk. The desk answers those beside a running turn (see the note on `desk_runtime.py`). A command belongs in `_INSTANT_COMMANDS` only if it changes nothing, so it can safely run at the same time as a model turn.

## /context, /tools, /skills and /subagents, since 2026-10-18

These copy what Claude Code, OpenClaw and Hermes offer under the same names, and they are text versions of the web page's side panel, for Telegram. All four only read, so they are instant commands.

`CommandParts` holds what these commands need beyond the desk: the tool registry, the subagent library and the desk's journal reader. It is a frozen dataclass so the desk builder can hand everything over in one argument instead of `DeskRuntime` growing one argument per command. `DeskRuntime` always puts its own tool registry into it, so the registry has one source.

- `/context` reports the snapshot of the backend that answered last (`ModelRouter.context_usage`). Claude's numbers are measured by Claude Code; the other backends' are estimates, and the reply says which.
- `/tools` shows the first sentence of each description, because the full descriptions of about 40 tools would fill several Telegram messages. `/tools full` gives them whole.
- `/skills` groups skills by `Skill.origin`, so the user can see which skills the desk wrote for itself. Skills hidden for a missing program or variable are listed with what they lack.
- `/subagents` reads today's `subagent_started` and `subagent_finished` events from the journal, because no run list is kept in memory. A start without a matching finish is shown as running; after a restart mid-run it would stay "running" for the rest of the day, which is acceptable for a read-out.

## /think, since 2026-10-18

`/think` copies OpenClaw's `/think` and Claude Code's `/effort`. It replaced the "later milestone" placeholder. The levels are the effort levels Claude Code accepts (low, medium, high, xhigh, max) plus `off`, and `default` goes back to `trading_agent.toml`.

The level applies to every backend of this desk, because a fallback model should think about as hard as the model it replaces. Each desk builds its own turn runners, so other desks are not affected, even when they share a backend entry in `trading_agent.toml`.

It lasts until the gateway restarts. That matches `/model`, and it keeps `trading_agent.toml` as the place where lasting settings live. `/think` is queued like other commands that change the desk, so it never lands in the middle of a turn.

## /btw, since 2026-10-18

`/btw` copies the side question of Claude Code, OpenClaw and Hermes. The use on a trading desk is asking "why did you take that trade?" without the question and answer becoming part of the conversation the desk trades from.

It is a background command (`is_background`): the desk answers it in its own task, like an instant command, so it neither waits for nor interrupts a running turn. Only one background command runs per desk at a time, tracked in `_background_command`, because each one costs a model call and two at once from a phone are almost always a double tap. All handlers run on the one event loop thread, so the check-then-set needs no lock.

A paused desk asks no model, so `/btw` respects `/pause` like a model turn does.

The answer names the backend that gave it, because a fallback model may lack the latest exchanges (see the note on `model_router.py`).

## /review, since 2026-10-18

`/review` borrows Hermes's `/review`, which spawns a reviewer subagent for recent work, and points it at the desk's trading. It runs the existing `trade_reviewer` subagent through the desk's `SubagentRunner.run_one`, the same call the cron scheduler uses for subagent jobs, so it gets the reviewer's own tools, model order and five-minute limit.

The task lists today's `order` and `fill` events from the desk's journal, because the journal is the only record that ties each order to the desk, dry runs included. UBI's order book is shared by every desk. The reviewer can still call `get_orders` and `get_portfolio` for live prices and positions, so the task does not repeat the profit and loss. At most 200 events are listed, the latest ones, so a busy scalper day cannot overflow the reviewer's context.

With no orders today it answers at once and starts no subagent, because a review of nothing would only spend the subscription. It is a background command, sharing the one-at-a-time guard with `/btw` through `_one_at_a_time`, because a review can take minutes.
