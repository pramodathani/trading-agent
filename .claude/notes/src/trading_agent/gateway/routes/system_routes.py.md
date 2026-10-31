# system_routes.py

The configuration is returned with every value the secret redactor knows replaced. trading_agent.toml should hold no secrets, since they live in .env, but a user might paste a token into a URL by mistake, and the redactor already knows every value from .env and the tradingmachine environment file. The test puts a password inside a backend URL to show it is masked.

Usage is today's tokens per trader and backend from the usage tracker, plus the latest rate-limit report from each backend that sends one. Claude's report says whether the five-hour or weekly limit is close.

## Live trader names

The names are kept as given, not copied, and the gateway passes its live dictionary of traders, so a trader created after start-up appears here at once.
