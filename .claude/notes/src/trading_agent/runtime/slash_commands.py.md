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
