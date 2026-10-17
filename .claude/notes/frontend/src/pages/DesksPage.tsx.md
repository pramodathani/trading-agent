# DesksPage.tsx

The home page. Each card shows a desk's state, today's profit or loss from the risk engine's per-desk figures, any halt, its models in the order they will be tried, and the last thing it did since the page opened.

Flatten asks for a reason and runs the desk's own `flatten_desk` tool through the API, so it goes through the risk engine and the journal like the desk's own flatten. Pause and resume take effect at once.

The account figures are polled every 15 seconds; the desks' state is refreshed by the layout every 5 seconds and at once when a turn starts or ends.
