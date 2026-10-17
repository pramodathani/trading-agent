# command_job_runner.py

Command jobs run `bash -c <command>` through the desk's `BashSandbox.command` (a fresh process, not the desk's persistent bash session, so a scheduled command never interferes with the desk's own shell), with the sandbox's command timeout, keeping the last 4,000 characters of output.
