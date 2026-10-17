# AppLayout.tsx

The layout polls the desks every 5 seconds and shares the answer through `DesksContext`, so the header, the Desks page and the Chat page all agree on each desk's state without each asking separately. It also refreshes at once when a live event shows a turn starting or ending.

The header shows DRY RUN or LIVE ORDERS at all times, so the trading mode is never in doubt, and whether the live connection is open.
