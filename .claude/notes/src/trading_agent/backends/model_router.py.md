# model_router.py

Two changes on 2026-10-18 for the Claude → DeepSeek → Qwen → Gemma order:

1. A backend can say how long to leave it alone (`BackendUnavailableError.retry_after_seconds`). Claude passes the time until its subscription limit resets, and DeepSeek 15 minutes after running out of credit. The router then skips that backend until then and returns to it by itself, instead of retrying after 30 s, 1 min and every 5 min. The user chose to switch only when Claude refuses, not before a usage threshold.
2. When a backend fails partway through a turn, the next one is told which tool calls were already made for the trigger (from the trader's executor) and not to repeat them. Before this, a backend taking over redid the turn blind and could, for example, place an order a second time.

## Thinking, since 2026-10-18

`set_thinking` passes the level to every route, not only the first, so a fallback model inherits the user's choice. `thinking_lines` lists the routes in the order they will be tried, like `status_lines`.

## Side questions, since 2026-10-18

`side_question` asks the backend that answered last first, because only its conversation holds the whole session; a fallback backend may lack the exchanges it missed, which the router normally fills in with a hand-over that a side question does not get. A failure is not recorded with `record_failure`, so a failed side question never makes a backend wait for real turns. Nothing is passed to `_finish`, so the session's exchanges are unchanged.
