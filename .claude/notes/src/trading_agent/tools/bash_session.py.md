# bash_session.py

One bash process per desk stays running, so `cd` and `export` carry over between commands as in a real terminal, which is how Claude Code's own Bash tool behaves.

Each command is wrapped as `{ command } < /dev/null` followed by a `printf` of a random marker and the exit status. The braces keep the command in the same shell (so its `cd` persists), the redirection stops a command that reads the keyboard (`cat`) from swallowing the marker line, and the random marker cannot be faked by a command's own output. Trailing newlines are removed from the output, as bash's own `$(...)` does.

A command that exceeds `command_timeout_seconds` (120 by default) kills the whole session; the next command starts a fresh terminal, and the model is told that its folder and variables were reset and to use `bash_background` for long work. A lock makes parallel tool calls run their commands one after another.

Background jobs run under `nohup` with their output in `scratch/.background/<id>.log`. Their process ids belong to the sandbox's own process list, so they are checked from inside the session, and they end when the session restarts.
