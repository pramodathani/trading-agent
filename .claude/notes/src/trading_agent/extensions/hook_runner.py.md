# hook_runner.py

Hooks (block 28): the user's scripts, run as separate processes when events happen.

## Decisions

- **Folder per event.** `workspace/shared/hooks/<event>/` and each package's `hooks/<event>/`. Any event kind works as a folder name, plus two narrower names from the plan: `order_placed` (an order event with action "placed") and `risk_rejected` (a refused risk decision). The plan's other examples map to existing kinds: `trader_stopped` is a kind; `session_ended` is covered by `session_started`, whose payload names the previous session at a rollover.
- **Never on text pieces.** `text_delta` events are skipped, as in the journal.
- **Isolation.** A hook gets the event as JSON on stdin with secrets masked by the same redactor as the journal, and a minimal environment (HOME, LANG, LOGNAME, PATH, USER, plus TRADING_AGENT_EVENT and TRADING_AGENT_TRADER). Hooks are the user's own scripts, so they are not sandboxed, like git hooks.
- **Cannot hurt a trader.** At most four run at once, each for at most 30 seconds; failures, timeouts and missing interpreters are logged and nothing else happens. Hook failures are deliberately not published on the event bus, because an `error` hook reacting to its own failure could loop forever.
- **Found per event.** The folders are listed again for every event, so a hook added or a package installed while the gateway runs takes effect at once.

## A bug the live test found

The first version ran the hook by its path as found, relative to the project folder, but started it with its own folder as working directory, where that relative path does not exist: "could not start: [Errno 2] No such file or directory". The unit test used absolute paths and missed it. Hooks now run by their resolved path, and the test runs from a relative hooks folder as the gateway does; it fails on the old code and passes on the fix.

## Verified on 2026-10-17

With a demo package installed, its `session_started` hook ran when the gateway started, and its `risk_rejected` hook ran when the risk engine refused Claude's weekend order; both appended the event JSON to a log file.
