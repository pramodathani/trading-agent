# SessionsPage.tsx

The page shows the three layers of a trader's memory: the session log (one per trading day, holding each finished turn's question and answer), the daily summaries written at each rollover, and the notes the trader writes after its turns. The search box runs the same search as the trader's `search_sessions` tool, so the user finds what the trader would find.

Questions are shown with their context line (time, what woke the trader, market status), because that is exactly what the model saw.
