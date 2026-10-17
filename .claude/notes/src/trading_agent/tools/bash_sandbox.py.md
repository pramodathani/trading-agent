# bash_sandbox.py

The user chose a full shell with no approvals, and the plan put it inside bwrap so that the shell cannot get around the risk engine. What the sandbox must therefore prevent is reaching the broker or rewriting the rules; everything else it may do.

## What is hidden, and why (checked on 2026-10-17)

- Every `.env` under `~/Projects` and the whole `unified_broker_interface` folder: they hold the credentials for UBI, MongoDB and Redis. Without them the shell cannot trade: UBI answered 401 to every route without a token, including `/api/orders/place`, and the MongoDB servers on ports 1003, 2003 and 3003 and the Redis servers on 1002 and 2002 all refused unauthenticated access.
- `/run/docker.sock`: the user is in the `docker` group, so with the socket the shell could start a container that mounts any database's files.
- `/run/user`: the user's session bus lives there, and through it `systemd-run --user` could start programs outside the sandbox.
- `~/.claude`, `~/.claude.json`, `~/.config/anthropic`, `~/.hermes`, `~/.ssh`, `~/.gnupg`, `~/.config/gh`, `~/.git-credentials`, `~/.docker`, `~/.ollama`: logins and keys.
- The environment is cleared (`--clearenv`), so the gateway's token and the Claude token do not reach the shell.

The network is shared on purpose, so the shell can use pip, curl and APIs. A separate network namespace would also cut off the internet.

## Mechanics

Each hidden path is resolved first and nested ones are dropped. On this machine `/var/run` is a link to `/run`, so `/var/run/docker.sock` and `/run/docker.sock` are the same file, and bwrap refused to cover one file twice; the first probe failed for exactly that reason. A file is covered with `/dev/null` and a folder with an empty tmpfs.

`--unshare-pid` gives the sandbox its own process list (four processes were visible in the probe), so the shell cannot see or signal the gateway. `--die-with-parent` ends the sandbox when the gateway ends. HOME is a folder inside the desk's scratch folder, so tools that write to HOME work.

Hidden paths are expanded when the desk is built, so a `.env` created later is only hidden after the gateway restarts.

## Passed environment variables (milestone 13)

The sandbox still starts with an empty environment. `[sandbox] passed_environment` names the variables to copy in from the gateway, for skills whose scripts need an API key or similar; only names the user lists there are passed, and only when set. Naming a variable there is a deliberate decision to let the desk's shell, and so the model, read it. The values appear on bwrap's command line, which other processes of the same user can see; the gateway already holds them in its own environment, so this exposes nothing new to that user. The skill library checks skills' environment needs against this list.
