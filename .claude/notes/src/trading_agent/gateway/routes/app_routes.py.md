# app_routes.py

The list checks every app at once, so a slow app does not delay the others. Start, stop and restart are limited to units named by an installed package's app.toml; an unknown action is 400 and a systemctl failure is 502, because the gateway is fine and the unit is what failed.
