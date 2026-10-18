# pending_files.py

Files upload as soon as they are added, as on the web page, so sending does not wait for a large upload that could have run while the message was being typed. `ready_ids` waits at most two minutes for uploads still running; files that failed are reported and left out, and the message still goes.

A message that carries files is always queued by the gateway rather than steering a running turn (`DeskRuntime._can_steer`), so a file sent while the desk works becomes the next turn.
