# TradersPage.tsx

The home page. Each card shows a trader's state, today's profit or loss from the risk engine's per-trader figures, any halt, its models in the order they will be tried, and the last thing it did since the page opened.

Flatten asks for a reason and runs the trader's own `flatten_trader` tool through the API, so it goes through the risk engine and the journal like the trader's own flatten. Pause and resume take effect at once.

The account figures are polled every 15 seconds; the traders' state is refreshed by the layout every 5 seconds and at once when a turn starts or ends.
