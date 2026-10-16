# workspace_layout.py

All paths into the workspace live in this one class, so later milestones (memory, journal, skills) add a method here instead of building paths by hand.

`create_missing` never overwrites a file. It runs at every start, so a deleted file is recreated from its template while every edited file is left alone.

A file is still a template while it contains the exact line `Status: template, not filled in yet.`. The prompt builder uses that to decide whether to add the first-run interview, and the interview's instructions tell the model to remove the line from every file it proposes, so accepting the proposals ends the interview.

The templates ship inside the package (`workspace/templates/`) and are read with `importlib.resources`, so they are found whatever the working directory is.
