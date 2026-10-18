# composer.py

The box is a Textual `TextArea` whose `_on_key` is overridden, because `TextArea` inserts a newline for Enter in `_on_key` before any binding could see it. Which keys arrive as `shift+enter` depends on the terminal: Kitty, WezTerm, Ghostty and others report it, many do not, so Ctrl+J and a backslash before Enter are kept as the always-working ways to add a line, as in Claude Code.

`?` is caught here, not as a screen binding, because the text area takes every printable key first.

Ctrl+V is taken over to attach a clipboard picture, and falls back to the text area's own paste. Backspace in an empty box removes the newest attached file, which plays the part of the web page's × on a file chip.
