# SettingsPage.tsx

Read-only, because the gateway reads trading_agent.toml once at start and changing it in a running gateway would mean the page and the gateway disagree. Each top-level setting gets its own panel. Secrets are never in the file, and anything matching a known secret is masked by the gateway before it is sent.
