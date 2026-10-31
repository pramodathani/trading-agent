# Your files

You instruct the traders with plain Markdown files. The traders read them at every turn, and they can never change them: they can only propose a new version, which you accept or reject on the Files page.

| File | Where | What it says |
|---|---|---|
| `Agents.md` | `workspace/shared/` | How every trader should work: its tools, its habits, what it may and may not do |
| `User.md` | `workspace/shared/` | Who you are: your capital, your risk appetite, your markets, your schedule and what you want reported |
| `TradingRules.md` | `workspace/shared/` | The strategies, and the hard limits the risk engine enforces |
| `Persona.md` | `workspace/traders/<trader>/` | One trader's style, holding period, products and cadence |

<figure class="diagram">
--8<-- "docs/assets/diagrams/prompt-builder.svg"
<figcaption>Your files flow into each trader's instructions through the prompt builder, for the local models and for Claude alike. The blue dot is a trader proposing a change, which waits in proposals/ until you decide.</figcaption>
</figure>

The prompt builder caps each file at 20,000 characters and all of them together at 60,000, so a long file cannot crowd out the conversation.

## Proposals

When a trader thinks one of your files should change, it calls `propose_file_change` with the complete new text and its reason. The proposal appears on the Files page with a coloured diff, and on the command line:

```bash
bin/trading-agent proposals list
bin/trading-agent proposals accept <id>
```

Accepting a proposal for TradingRules.md is checked like any edit: if the risk engine could not read the new limits, nothing is saved.

## The traders' own files

Each trader may write only inside its own `memory/`, `notes/` and `scratch/` folders, and its own `Memory.md` and skills. It writes one to three notes after a turn in which it learned something, and at each day's rollover it folds the day's notes into Memory.md. You can read and correct Memory.md on the Files page; a checkpoint is taken first.
