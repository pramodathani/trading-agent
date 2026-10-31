# Skills

A **skill** is a written procedure in the open `SKILL.md` format, with optional scripts and reference files beside it. Only each skill's name and one-line description are in a trader's instructions; when a task matches, the trader loads the whole skill with `load_skill` and follows it. You can also ask for one directly with `/<skill-name>`.

<figure class="diagram">
--8<-- "docs/assets/diagrams/skills.svg"
<figcaption>Your installed skills and the trader's own skills are offered to each turn. Each use is recorded; the curator patches, merges and archives the trader's own skills, and the skill writer takes a checkpoint before every change.</figcaption>
</figure>

## Two homes

| Skills | Where | Who changes them |
|---|---|---|
| Yours | `workspace/shared/skills/installed/`, and the `skills/` folder of each package | Only you, with `bin/trading-agent skills import <folder, zip or git URL>` |
| The trader's own | `workspace/traders/<trader>/skills/agent/` | The trader, with `skill_create`, `skill_patch` and `skill_archive` |

A skill can say which programs and environment variables it needs. When one is missing, the skill is hidden from the trader, and the Skills page lists it as hidden with what it lacks.

## Skills the trader writes

After a multi-step task it will need again, a trader is nudged to write the procedure down as a skill. Each use is recorded with whether a tool failed afterwards or the turn ended in an error. After the close, the curator looks at the trader's own skills: it patches the ones that keep going wrong, merges duplicates, and archives skills not used for 30 days. A checkpoint is taken before each change, so any of them can be undone.

On 17 October 2026, Claude wrote a `range-check` skill from a run on HDFCBANK, and Qwen then followed it on SBIN through `/range-check`.
