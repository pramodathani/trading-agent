# Sridhara as a trading-agent app

This package adds sridhara to trading-agent's sidebar without changing sridhara. It holds only `app.toml`, which says where sridhara's page is and which systemd user unit runs it.

Install it with:

```bash
bin/trading-agent packages install packages/sridhara
```

Sridhara keeps running as its own service on port 8095, with its own login. trading-agent shows its page, says whether it answers, and can start, stop or restart `sridhara.service`. If sridhara is not yet a service on this machine, `bin/trading-agent apps enable sridhara` links the unit file from sridhara's repository and starts it.
