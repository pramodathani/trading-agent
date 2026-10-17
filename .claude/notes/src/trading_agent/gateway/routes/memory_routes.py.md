# memory_routes.py

Session ids and days arrive from the browser and become file names, so both are checked against strict patterns before any file is opened. Without that, an id such as `../../.env` could read outside the sessions folder.

Journal reads are capped at 2000 events so a busy day cannot produce an enormous answer. The search route reuses the `search_sessions` tool's own search, so the web page finds the same things the desk does.

The live test on 2026-10-17 showed today's sessions with 0 exchanges. That was correct: both session files were empty after the morning's rollover tests.
