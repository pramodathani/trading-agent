# cron_job_store.py

`desks/<desk>/cron/`: jobs.json (definitions), state.json (each job's last scheduled run, built-in ones included) and runs.jsonl (one line per run or skip). JSON instead of the plan's TOML because the desk's tools write the file and Python's standard library cannot write TOML. Writes go through a temporary file and a rename, so a crash leaves the old file. The folder is ignored by git.

## Recent runs (milestone 17)

`recent_runs` reads only the last lines of runs.jsonl for the jobs page. A damaged line is skipped, as elsewhere in the store.
