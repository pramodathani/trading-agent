# session_keeper.py

The session keeper does the daily rollover (block 32) and seeds each new session with the previous summary.

## When the rollover happens

Lazily, at the first model turn on a new India date: `prepare` compares the router's session date with today's. There is no scheduler yet; milestone 15's cron scheduler will add an after-the-close job that calls `roll_over` directly, so the summary is written at 15:45 rather than when the first message of the next morning arrives. Commands (such as `/status`) and paused desks never trigger it, because `DeskRuntime._answer` only calls `prepare` before a model turn.

## The summary turn

The summary is written by the desk's own model, as one more turn of the old session, because that session is the only place that holds the whole day in context. The request asks for two things in order: fold the day's notes into Memory.md (the "after the close, notes are consolidated into Memory.md" step of block 34), then reply with a summary under 400 words. The reply becomes `sessions/summaries/<date>.md`.

The turn goes through the router, so a Claude outage falls back to Qwen or Gemma as usual. If every backend is down, `_fallback_summary` lists the session's exchanges, shortened, so the next session still learns something and the rollover never blocks the desk.

An empty session (no finished exchanges) gets no summary, so a desk that slept through a holiday does not write empty files.

## Seeding

While the router's current session has no exchanges, the latest summary is put in front of the trigger's text. The seed is placed before the India-time context line is added by `DeskRuntime._with_context`, so the context line stays the first line of the message, as `Agents.md` promises. The seed is part of the first exchange's trigger text, so it is also in the session log and reaches a local backend through the hand-over.

## Events

`session_started` is published with reason `first`, `resumed` or `daily_rollover`, the session id, the number of exchanges, and for a rollover the previous session id and the summary file. The journal keeps these, so the session history can be read from the journal alone.

## Verified on 2026-10-17

The state file was backdated to 2026-10-16 and the gateway restarted. The first message made Claude write the summary, rewrite Memory.md under three headings (one checkpoint taken before), and the new session `2026-10-17-2` started with a fresh Claude session that knew the test codeword from the summary alone.

## Skill review (milestone 13)

With a curator, the rollover runs `_review_skills` after writing the summary: the code archives idle skills, then the review turn runs in the old session. See `skills/skill_curator.py.md`.
