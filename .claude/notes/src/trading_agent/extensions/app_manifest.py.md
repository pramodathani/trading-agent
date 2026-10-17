# app_manifest.py

The plan says a package can hold "an app.toml (a web page plus a systemd unit)", and that sridhara, order_visualizer and instruments_explorer become packages "without changing their code". So an app.toml only describes an app that already exists: where its page is and which systemd user unit runs it. Nothing in the package runs inside the gateway.

## Checks when the file is read

- `url` and `health_url` must be http or https addresses, so a package cannot make the web page frame a `file:` or `javascript:` address.
- `unit` must look like a plain service unit name (letters, digits, `@`, `.`, `_`, `-`, ending in `.service`), so no value can reach systemctl as an option such as `--now` or as a path.
- Unknown keys are refused, so a typing mistake such as `open-in` is reported instead of being silently ignored.

## unit_file

Optional, for apps not yet installed as services. `%h` stands for the home folder, as in systemd's own unit files, which keeps the sample package free of a hard-coded /home/pramod. A relative path is inside the package.

## open_in

"frame" shows the app inside trading-agent. That works for apps on the same machine because the browser treats 127.0.0.1 on any port as the same site for cookies, so an app's own login cookie still works inside the frame. "tab" is for apps that refuse to be framed.
