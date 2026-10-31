# market_status.py

The market part of the context line at the top of every message to a trader: whether NSE equities trade today (open now, not open yet, closed for the day, or closed and why), the next trading day, and any weekday holiday in the next seven days.

Added after the live test of milestone 16: asked about its routine on a Saturday, the positional trader said it would write "Tuesday's plan" on Monday, but Tuesday 20 October 2026 is Dussehra. With the line, the same trader answered that its Monday plan would be for Wednesday 21 October because of the holiday. A line in every message costs a few tokens and saves a calendar tool call on nearly every turn.
