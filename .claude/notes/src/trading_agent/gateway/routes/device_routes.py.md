# device_routes.py

The Firebase tokens are never returned by the API, only each phone's random `device_id`, name and time, so a page or a log cannot leak a token. `problem` explains why push is off (switched off in the toml, no key path in `.env`, or an unreadable key), which the Settings page's Phones panel shows. The test route sends to the one phone whose button was pressed.
