# attachable_files.py

The accepted types and the 20 MB limit copy the web page's `ACCEPTED_FILES` and the gateway's attachment store, so a file is refused before uploading rather than after.

Dragging files onto a terminal window does not send a drop event: the terminal pastes the files' paths. GNOME Terminal quotes each path in single quotes, Kitty and WezTerm escape spaces with backslashes, and some send file:// addresses, so `from_paste` reads all three with `shlex`. Pasted text is treated as files only when every word is an existing file, so pasting an ordinary sentence that happens to contain a path still pastes the sentence.
