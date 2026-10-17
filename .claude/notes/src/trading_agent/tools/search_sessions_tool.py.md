# search_sessions_tool.py

The model-facing wrapper around `memory/session_search.py`. It formats each hit as `[date · kind]` followed by the snippet, says whether the hits contain every keyword or only some, and refuses a query with no letters or digits. The search runs in `asyncio.to_thread` because it reads many files.

Verified on 2026-10-17: Qwen searched "INFY refused" and correctly reported the milestone 10 refusal and its date, after the search was changed to read exchanges from the journal (see the note on `session_search.py`).
