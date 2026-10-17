# app_commands.py

`apps enable` links the package's unit file into the user's systemd (when systemd does not know the unit yet) and runs `enable --now`, so the app starts at every login. The unit file's name must match the unit, so a package cannot link a file under one name and run another. `apps list` shows the same states as the web page, for use without a browser.
