# chat_screen.py

## Keys

The keys follow Claude Code where the meaning carries over: Enter sends, Esc stops the running turn (it sends `/stop`, which the desk handles at once), Ctrl+C clears, then stops, then exits on a second press, Ctrl+D exits on a second press when the box is empty, Ctrl+O opens every tool call, Ctrl+R searches history and `?` in the empty box lists the keys. The desk picker is Alt+D, not Ctrl+K as first planned, because Ctrl+K is the text area's delete-to-end-of-line. Ctrl+C and Ctrl+D are priority bindings so they work while the text area has the focus; Ctrl+D falls back to deleting forward when the box has text.

## Terminal commands and desk commands

Only `/desk`, `/model` with no argument, `/theme`, `/keys`, `/exit` and `/quit` are handled by the terminal. Everything else, including `/model qwen`, goes to the desk, so the terminal never needs to know a desk command to support it. The menu lists the terminal's own commands first, then `GET /api/desks/{desk}/commands`, leaving out desk entries that a terminal command shadows.

## Loading and live events

`load_desk` reads the desk's journal of today while live events are held, then adds both; `ChatTranscript` drops duplicates. After a reconnect the chat is loaded again, because the stream never replays what was missed.

## Scrolling

The transcript uses Textual's `anchor()`, which keeps a scroll area at its bottom while content grows until the user scrolls away. `scroll_end()` was tried first and left the view short of the bottom, because Markdown answers finish their layout after the call. The anchor is set again whenever an event arrives while the view is at the bottom, and when the user sends a message.

## Shutdown

`_show_status` looks its widgets up with `query()` and returns when they are gone, because a desk poll can finish after the screen's widgets have been removed at exit; `query_one` raised there and failed the worker.
