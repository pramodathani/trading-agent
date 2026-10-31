# chat_screen.py

## Keys

The keys follow Claude Code where the meaning carries over: Enter sends, Esc stops the running turn (it sends `/stop`, which the trader handles at once), Ctrl+C clears, then stops, then exits on a second press, Ctrl+D exits on a second press when the box is empty, Ctrl+O opens every tool call, Ctrl+R searches history and `?` in the empty box lists the keys. The trader picker is Alt+D, not Ctrl+K as first planned, because Ctrl+K is the text area's delete-to-end-of-line. Ctrl+C and Ctrl+D are priority bindings so they work while the text area has the focus; Ctrl+D falls back to deleting forward when the box has text.

## Terminal commands and trader commands

Only `/trader`, `/model` with no argument, `/theme`, `/keys`, `/exit` and `/quit` are handled by the terminal. Everything else, including `/model qwen`, goes to the trader, so the terminal never needs to know a trader command to support it. The menu lists the terminal's own commands first, then `GET /api/traders/{trader}/commands`, leaving out trader entries that a terminal command shadows.

## Loading and live events

`load_trader` reads the trader's journal of today while live events are held, then adds both; `ChatTranscript` drops duplicates. After a reconnect the chat is loaded again, because the stream never replays what was missed.

## Scrolling

The transcript uses Textual's `anchor()`, which keeps a scroll area at its bottom while content grows until the user scrolls away. `scroll_end()` was tried first and left the view short of the bottom, because Markdown answers finish their layout after the call. The anchor is set again whenever an event arrives while the view is at the bottom, and when the user sends a message.

## Shutdown

`_show_status` looks its widgets up with `query()` and returns when they are gone, because a trader poll can finish after the screen's widgets have been removed at exit; `query_one` raised there and failed the worker.

## Attaching files

`@path` words that name files are removed from the message and their files go with it; a typed `@` opens the menu of files and folders, and picking a folder keeps the menu open inside it. `/attach path` and dropped files wait in the tray for the next message. The Ctrl+V handler runs in a thread because the clipboard programs block; it reaches the screen only through `call_from_thread`. The screen's method is `_attach_files`, not `_attach`: Textual calls a widget's `_attach` when it adds the widget to the screen, and the first version broke the screen's own mounting.
