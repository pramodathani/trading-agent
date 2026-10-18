# Commands

Everything the web page does can also be done from a terminal with `bin/trading-agent`. Run any command with `--help` for its options.

| Command | What it does |
|---|---|
| `serve` | Runs the gateway and its desks; the service normally does this |
| `doctor` | Checks everything the agent depends on |
| `preflight` | The doctor plus the going-live checks, with a verdict |
| `send [--desk NAME] TEXT` | Sends a message or slash command to a desk, general unless named, and prints the turn |
| `proposals list`, `accept ID`, `reject ID` | The desks' proposed changes to your files |
| `checkpoints list [--desk NAME]`, `restore [--desk NAME] ID` | Snapshots of a desk's own files; the desk is general unless named |
| `skills list`, `import SOURCE` | Your skills and the desks' own; import from a folder, zip or git URL |
| `mcp list` | Each MCP server's state and tools |
| `packages install SOURCE`, `list`, `remove NAME` | Packages of skills, subagents, MCP servers, hooks and apps |
| `apps list`, `enable NAME`, `disable NAME` | The packages' web apps and their systemd units |
| `subagents list` | The subagent definitions |
| `pairing list`, `approve CODE`, `revoke CHAT_ID` | Telegram chats allowed to command the desks |

`bin/trading-agent` changes to the project folder first, so it can be run from anywhere.
