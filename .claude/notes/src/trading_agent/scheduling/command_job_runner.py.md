# command_job_runner.py

Command jobs run `bash -c <command>` through the trader's `BashSandbox.command` (a fresh process, not the trader's persistent bash session, so a scheduled command never interferes with the trader's own shell), with the sandbox's command timeout, keeping the last 4,000 characters of output.
