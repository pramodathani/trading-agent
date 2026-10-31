# skill_commands.py

`trading-agent skills list` prints, per trader, each usable skill with its origin and each hidden skill with what it needs. It checks needs against the variables the sandbox would pass, built from `[sandbox] passed_environment`, exactly as the running traders do. `skills import` prints one line per skill folder found, and exits with status 1 if any was invalid.
