# proposal_store.py

The user decided that the agent may change only its own notes, memory and skills. The proposal store is how it still contributes to the user's files: it saves the complete new text of one file with a reason, and only `trading-agent proposals accept` writes it.

Each proposal is one JSON file in the proposing trader's `proposals/` folder. Accepting keeps a copy of the replaced file in `proposals/replaced/`, so an accepted proposal can always be undone by hand. A proposal holds the whole file rather than a patch, because models are more reliable at writing a whole short file than at writing a correct diff, and the user sees the change as a diff with `proposals show`.

Proposals are ignored by git; the user's files themselves are tracked.
