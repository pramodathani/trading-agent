# package_installer.py

`trading-agent packages install|list|remove`. The plan named the command `trading-agent install`; it sits under `packages` to match `skills`, `checkpoints` and `proposals`.

## Decisions

- **Same sources as skills** (folder, zip file, git URL), through the shared `source_fetcher.py`.
- **Name.** From `[package] name` in package.toml, else the source's last path part without `.git` or `.zip`, lower-cased. It must be a safe folder name.
- **Checks before copying.** The folder must hold at least one package part, and its mcp_servers.json must be valid, so a broken package cannot stop the gateway from starting (an invalid MCP file is a start-up error).
- **Warnings, not refusals.** Prompt-injection findings in its text files and hook files that are not executable are reported; installing is the user's decision.
- **No silent replace.** An installed package of the same name is kept unless `--replace` is given.
- **What needs a restart.** Skills and hooks take effect immediately; MCP servers start with the gateway, so the command says to restart it.

## Verified on 2026-10-17

A demo package with a skill, an MCP server (a copy of the test server, run as `python server.py` from the package folder) and two hooks installed, showed up in `packages list` and `skills list`, its server connected with 3 tools, and Claude called it to add 19 and 23. It was removed afterwards.
