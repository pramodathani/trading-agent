# turn_runner.py

`close` was added in milestone 3 so that a runner which starts something, like a Claude Code process, can stop it when its desk stops. The default does nothing, so runners that start nothing need no code for it.

## saved_state and restore_state (milestone 11)

Two optional hooks for crash recovery. The defaults say "nothing to save" and "could not resume", which is right for any runner whose conversation lives only in memory. The model router calls them; the desk runtime never does.
