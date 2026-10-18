# Commands

`bin/trading-agent` with no subcommand opens [the terminal program](terminal.md), a full-screen chat that does everything the web page does. The subcommands below are for scripts, setup and checks. Run any command with `--help` for its options.

| Command | What it does |
|---|---|
| (none) | Opens the terminal program on the desk used last, or the one named with `--desk NAME` |
| `-p TEXT [--desk NAME] [--output-format text\|json\|stream-json]` | Sends one message or slash command and prints the reply, like `claude -p`; text piped on standard input goes before it |
| `serve` | Runs the gateway and its desks; the service normally does this |
| `doctor` | Checks everything the agent depends on |
| `preflight` | The doctor plus the going-live checks, with a verdict |
| `send [--desk NAME] TEXT` | The same as `-p` with the text format; kept for scripts that use it |
| `proposals list`, `accept ID`, `reject ID` | The desks' proposed changes to your files |
| `checkpoints list [--desk NAME]`, `restore [--desk NAME] ID` | Snapshots of a desk's own files; the desk is general unless named |
| `skills list`, `import SOURCE` | Your skills and the desks' own; import from a folder, zip or git URL |
| `mcp list` | Each MCP server's state and tools |
| `packages install SOURCE`, `list`, `remove NAME` | Packages of skills, subagents, MCP servers, hooks and apps |
| `apps list`, `enable NAME`, `disable NAME` | The packages' web apps and their systemd units |
| `subagents list` | The subagent definitions |
| `pairing list`, `approve CODE`, `revoke CHAT_ID` | Telegram chats allowed to command the desks |

`bin/trading-agent` changes to the project folder first, so it can be run from anywhere.
