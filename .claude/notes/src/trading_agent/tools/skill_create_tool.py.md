# skill_create_tool.py

The model-facing side of `SkillWriter.create`. The description asks for numbered steps that name tools and checks, and no facts that go stale such as today's prices, because a skill is reused on other days and other stocks. `reason` is required so the ledger explains every skill.

Verified on 2026-10-17: asked to work out and save a 30-day range routine, Claude tried it on HDFCBANK and created `range-check` with six steps, declaring `python3` as a requirement because step 4 computes averages in `bash_run`. Qwen then followed it on SBIN through `/range-check`.
