# AppLayout.tsx

The layout polls the traders every 5 seconds and shares the answer through `TradersContext`, so the header, the Traders page and the Chat page all agree on each trader's state without each asking separately. It also refreshes at once when a live event shows a turn starting or ending.

The header shows DRY RUN or LIVE ORDERS at all times, so the trading mode is never in doubt, and whether the live connection is open.
