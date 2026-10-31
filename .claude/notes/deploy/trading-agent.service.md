# deploy/trading-agent.service

The plan's supervisor: a systemd user unit, like sridhara's, so the gateway starts at boot and restarts after a crash. The user's account has lingering on, so user units run without a login session.

- `Restart=always` with `RestartSec=10`: a crash costs ten seconds. Tested on 2026-10-17 by killing the gateway with SIGKILL: systemd started a new process eleven seconds later, every trader resumed its session, and the scalper still remembered a word it was given before the crash.
- `PATH` is set explicitly, because a systemd user unit gets a minimal one; `~/.local/bin` is first so the user's tools are found. Claude Code itself does not depend on it, because claude-agent-sdk carries its own copy of the CLI.
- `TimeoutStopSec=60` gives the traders and the Claude Code processes time to close on a stop or restart before systemd kills them.
- The unit is linked, not copied, into ~/.config/systemd/user, so editing this file and running `systemctl --user daemon-reload` updates it.

Stopping the service closes nothing at the broker: orders and bracket stops held by UBI stay in place. docs/going_live.md says so in its table of ways to stop.
