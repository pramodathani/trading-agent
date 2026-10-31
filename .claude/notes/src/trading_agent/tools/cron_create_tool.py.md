# cron_create_tool.py

Repeating jobs created by the trader. It takes either `instructions` (an agent job) or `command` (a command job), never both, and the kind follows from which is given.

The first version had one `instructions` field for both and a `kind` switch. In the live test Qwen made a command job whose command was the sentence "Run the shell command: date", which failed every minute with exit code 127. Separate fields, with a description that says to put only the command there, fixed it: Qwen then created `command: "date"` and the job printed the date.

The tool refuses a schedule that never runs with the chosen options, and answers with the job's id and next three runs.
