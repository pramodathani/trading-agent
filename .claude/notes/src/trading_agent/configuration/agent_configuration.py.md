# agent_configuration.py

Every model uses `extra='forbid'`, so a misspelt key such as `modde` is reported rather than silently ignored. A trading agent whose `mode` setting was mistyped and quietly fell back to a default would be dangerous in either direction.

Desk names are limited to lower-case letters, digits and underscores, because a desk name becomes a folder name, an order tag sent to UBI and part of web addresses.

The `base_url` rule is a validator rather than a separate model per backend kind, because only that one field differs between kinds today. If the kinds grow apart, each can become its own model.
