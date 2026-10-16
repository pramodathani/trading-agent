# bubblewrap_check.py

The check starts a real, empty sandbox rather than only looking for the `bwrap` program, because some Ubuntu releases restrict the unprivileged user namespaces that bwrap relies on, and the program can be installed yet unable to start a sandbox. On 2026-10-16 the sandbox started on this machine.
