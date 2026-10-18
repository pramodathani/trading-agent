# side_panel.py

The panel copies `frontend/src/sidePanel/SidePanel.tsx`: the same eight cards, the same polling intervals (context 20 s, account and open orders 15 s, MCP servers 60 s) and the same events that trigger an early refresh. It reads the same routes as the web page, so its numbers are the web page's numbers.

## The `_context` freeze

The first version kept the context document in `self._context`. Textual's `MessagePump` has a method of that name, which its message loop calls for every message; replacing it made the panel's loop fail at its first message, and the whole screen then waited for the panel for ever, with no error shown. The attribute is now `_context_document`, and `tests/test_terminal_attribute_names.py` fails whenever a class of the terminal package assigns a name that Textual's own classes use. The same check found `TerminalApplication._themes` (App's theme registry) and `ModelPicker._options`, which were renamed too.

## Folded cards

Folding is remembered by card name in `TerminalSettings.collapsed_cards`. The folds inside the Tools card are not remembered; `_remember` only acts on `SideCard`s.
