# terminal_application.py

The program owns the one event stream connection and the desk polling, and hands both to the chat screen, so later screens (side panel, other pages) can take the same events without opening their own sockets. Desk states are read every 5 seconds, as the web page does, and again after the events that change them, so the status line and the "working" placeholder follow a turn closely.

A refused token ends the program with exit code 1 and a message printed after the screen closes (`problem`), because a message printed while Textual owns the terminal would be lost.

The theme and the last desk are remembered in `TerminalSettings`, outside the repository, because they are one person's preferences, not configuration.
