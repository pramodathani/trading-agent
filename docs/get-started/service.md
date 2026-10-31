# The service

An agent that trades on its own must keep running when nobody is watching. trading-agent runs as the systemd user service `trading-agent.service`: systemd starts it at boot, restarts it ten seconds after a crash, and the traders resume their conversations.

<figure class="diagram">
--8<-- "docs/assets/diagrams/service.svg"
<figcaption>Orange dots are systemd starting the gateway, a crash, and systemd starting it again; blue dots are the traders' sessions coming back each time. The panel on the right is the going-live checklist that <code>bin/trading-agent preflight</code> reports.</figcaption>
</figure>

## Installing it

The unit file is `deploy/trading-agent.service`. Link it into your systemd, then enable and start it:

```bash
systemctl --user link $PWD/deploy/trading-agent.service
systemctl --user enable --now trading-agent
```

For a user service to run without anyone logged in, lingering must be on for your user, which it is on this machine:

```bash
loginctl show-user $USER -p Linger      # Linger=yes
```

## What it does

| Setting in the unit | Why |
|---|---|
| `ExecStart=%h/Projects/trading-agent/bin/trading-agent serve` | The same command you run by hand |
| `Restart=always`, `RestartSec=10` | A crash costs ten seconds |
| `Environment=PATH=%h/.local/bin:...` | A user service gets a minimal `PATH`; this keeps your tools reachable |
| `TimeoutStopSec=60` | Time for the traders and Claude Code processes to close |

On 17 October 2026 the gateway was killed with `kill -9`. systemd logged `status=9/KILL`, started a new process eleven seconds later, and the scalper trader still remembered a word it had been given before the crash.

## Everyday commands

```bash
systemctl --user status trading-agent      # running?
journalctl --user -u trading-agent -f      # the log, live
systemctl --user restart trading-agent     # after changing trading_agent.toml
systemctl --user stop trading-agent        # stops the traders; nothing is closed at the broker
```

Stopping the service stops the traders thinking, but orders and stops already held by UBI stay in place. To close positions, flatten a trader or fire the kill switch first, as [Going live](../going_live.md#how-to-stop) explains.
