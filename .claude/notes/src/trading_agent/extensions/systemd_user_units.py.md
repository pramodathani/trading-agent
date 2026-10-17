# systemd_user_units.py

The user's apps already run as systemd user units (sridhara.service, instruments-explorer.service), which start at login and restart after a crash. Reusing them means trading-agent never supervises another program itself.

Only `systemctl --user` is used, never root. Every public method checks the unit name first, so nothing but a plain service name reaches systemctl. Starting, stopping and restarting is allowed from the web page; linking and enabling a unit, which adds a program to the machine's start-up, is only offered as the `trading-agent apps enable` command.

Each systemctl call has a 30-second limit, so a hung unit cannot hang a web request forever.
