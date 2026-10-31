# trader_registry.py

Ported from research-agent's analyst registry (commit `5b243d7`).

## Shared dictionaries instead of copies

Most of the gateway was given the traders at start-up. To let a trader be created while the gateway runs, the registry owns the `traders`, `tool_registries` and `schedules` dictionaries and adds to them in place. Everything that held those dictionaries (route groups, the cron scheduler, the market watcher, Telegram, the request responder) sees a new trader at once. `TraderBuilder.trader_parts()` now returns the builder's own dictionary for the same reason. `AccountRoutes` and `SystemRoutes` used to copy the list of names; they now keep the live dictionary and read its keys on each request, which research-agent's `SystemRoutes` did not do.

## Starting and stopping

`GatewayApplication` used to start one task per trader in its lifespan. With a registry it calls `start()` and `stop()` instead, and a trader created between them gets its task at once. A lock keeps two creations or a creation and a retirement from interleaving.

## The introduction

A new trader is sent `INTRODUCTION` as a user message, asking it to restate its mandate, say what it would trade and how it would size and protect each trade, and propose a fuller Persona.md and, if needed, its own `[traders.<name>]` limits through `propose_file_change`. The user chose that a new trader may trade under the account-wide limits straight away, as an existing trader without an entry in TradingRules.md does, so the introduction does not tell it to wait.

## Retiring a trader that holds positions

Not in research-agent, whose analysts hold nothing. A retired trader's loop stops, so no one would watch its positions, its open orders or their fills. `retire` therefore refuses while the risk ledger says the trader owns an instrument or the order book lists an open order, and tells the user to flatten it first. The last running trader cannot be retired either, because Telegram and the web page need a trader to talk to.
