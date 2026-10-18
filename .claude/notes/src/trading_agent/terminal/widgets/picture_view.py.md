# picture_view.py

textual-image picks the best drawing method when it is imported: the Kitty graphics protocol (Kitty, WezTerm, Ghostty), Sixel (foot, mlterm, xterm with Sixel, and VS Code's terminal when `terminal.integrated.enableImages` is on), or coloured half-block characters everywhere else. In tests, with no terminal to ask, it falls back to grey shading characters, which is what the screenshots in this session show.

The view must be `width: 1fr`; with `width: auto` a vertical container gave itself no width and the picture never appeared, although it had loaded. The method that returns the file name is `_file_name`, not `_name`, because every Textual widget keeps its own name in `_name`.

The picture is saved by `AttachmentOpener` before it is drawn, so Enter can hand the same file to the desktop without downloading it again.
