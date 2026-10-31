# AppLayout.tsx

The layout polls the traders every 5 seconds and shares the answer through `TradersContext`, so the header, the Traders page and the Chat page all agree on each trader's state without each asking separately. It also refreshes at once when a live event shows a turn starting or ending.

The header shows DRY RUN or LIVE ORDERS at all times, so the trading mode is never in doubt, and whether the live connection is open.

## Created, retired and sleeping traders

`trader_created`, `trader_retired` and `trader_sleeping` refresh the trader list at once. A selected trader that is no longer running falls back to the first one, but only when the list of running traders changes, read through `selectedTraderStore.current()`, so choosing a just-created trader is not undone before the list has caught up.
