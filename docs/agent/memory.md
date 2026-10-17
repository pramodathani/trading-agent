# Memory

A desk remembers at four time scales. The table below lists them from the shortest to the longest.

| Layer | Kept in | Lasts |
|---|---|---|
| The conversation | The model's context, and the session log | Until it is compressed, or the day ends |
| The session | `sessions/<day>-<number>.jsonl`, one per trading day | Searchable for ever |
| Notes | `notes/<day>.md`, one to three lessons after a turn | Folded into Memory.md at the rollover |
| Memory.md | The desk's lasting lessons, read at every turn | Until the desk or you change it |

<figure class="diagram">
--8<-- "docs/assets/diagrams/memory.svg"
<figcaption>The session keeper resumes or rolls over the desk's session before each turn; the memory tools write the desk's own files, and every write is checkpointed first. The blue dots are what comes back from the session store and the journal.</figcaption>
</figure>

## Restarts and the daily rollover

When the gateway starts, each desk resumes the session it saved. At 15:45 on trading days, and at the first turn of a new day if the gateway was down, the desk summarises the day, folds its notes into Memory.md, and starts a fresh session whose first message carries the summary. The summaries are on the Sessions page.

## Searching the past

`search_sessions` lets a desk ask its own past, such as "what did I do last time NIFTY gapped down?". It searches earlier exchanges, daily summaries, notes, and the journal of orders, refusals and fills. The Sessions page offers the same search.

## Checkpoints

A snapshot of the desk's own files (Memory.md, memory/, notes/ and its own skills) is taken before every change, by the desk, the curator or you, in a git repository of its own at `workspace/.checkpoints/<desk>.git`. Restoring one snapshots the current files first, so a restore can itself be undone. Your own files are not part of it.

## Context compression

A model's context window is finite. Past 70% of it, before the next turn, the desk first gets a silent turn to save what matters to its memory, and then the older part of the conversation is replaced by a summary. Past 85% in the middle of a long turn, the conversation is compressed at once, without the flush.

<figure class="diagram">
--8<-- "docs/assets/diagrams/compression.svg"
<figcaption>Compression for Qwen and Gemma: the memory-flush turn writes to the desk's own files, the conversation is summarised, and the turn runs on the fresh conversation. Claude does the same through Claude Code's own compaction, with a flush first.</figcaption>
</figure>

On 17 October 2026, Qwen kept RELIANCE's price and INFY's high and low through a compression, and Claude kept a 0.8% stop preference through `/compact`.
