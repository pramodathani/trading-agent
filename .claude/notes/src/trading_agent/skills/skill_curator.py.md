# skill_curator.py

The curator (block 24) runs once a day, inside the session keeper's rollover, right after the summary.

## Decisions

- **When**: at the rollover rather than on a timer, because the review turn then runs in the old session with the whole day in context: the model knows which procedure it repeated, or which skill step failed. When the cron scheduler arrives (milestone 15), the after-close job runs the same rollover.
- **Code half**: `archive_unused` archives the trader's own skills unused for `[skills] archive_after_days` (30). A skill never used counts from the last change to its `SKILL.md`, so a fresh skill gets a full 30 days.
- **Model half**: one review turn listing each own skill with uses, troubled uses and last use, asking for three things only when useful: patch a skill whose troubled uses the day explains, merge duplicates (create the merged skill, archive the others), and write down any procedure from the day worth repeating. This last point is the plan's "nudge to write a skill after a complex task", done once a day with full context instead of after every long turn, which would cost an extra model call each time and mostly produce skills nobody needs.
- Installed skills are never reviewed or changed; they belong to the user.
- A failed review turn is logged and the rollover carries on.

## Verified on 2026-10-17

After a backdated rollover, Claude received the review listing `range-check` (used once, not troubled) and replied "No skill changes", which was the right call.
