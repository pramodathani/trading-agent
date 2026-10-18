# clipboard_picture.py

The terminal itself cannot paste a picture: a terminal paste carries text only. Ctrl+V therefore asks the desktop's clipboard programs directly. On this machine the session is Wayland, `wl-paste` is not installed and `xclip` is; xclip reads the Wayland clipboard through XWayland for X11 programs, which covers most copies. Installing `wl-clipboard` would make it work for every Wayland program. When no picture is found, Ctrl+V pastes Textual's own clipboard, as the text area normally does; ordinary text paste with the terminal's own paste key is untouched.
