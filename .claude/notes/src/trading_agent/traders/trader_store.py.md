# trader_store.py

Ported from research-agent's analyst store (commit `5b243d7`, as it stood at `4428bda`), with the name limit raised to 200 characters as research-agent later did in `ec5c790`.

## Why each trader has its own record

Before this, the traders were a `[[traders]]` list in `trading_agent.toml`, so a trader could only be added by editing that file and restarting the gateway. Keeping each trader's settings in `workspace/traders/<name>/trader.toml` lets the gateway write a new trader's file while it runs, without rewriting the user's hand-edited configuration with its comments and ordering. `trading_agent.toml` keeps a `[traders]` table of defaults for new traders.

## What differs from research-agent

- A trader has a **mandate** (what it trades and how) instead of a research project and its source.
- The user chose that the creation form asks for the models, the heartbeat and the scheduled check times as well as the name and mandate. `heartbeat_minutes` is `None` for "use the default" and `0` for "no heartbeat", so a form or a Telegram command can say either.
- Scheduled check times are validated through the record's own pydantic model, and every problem is turned into a `TraderStoreError` naming the setting before any folder is made.
- The persona follows the starter personas' headings (style, how often to check, what never to do), so a new trader's prompt looks like the others'.

## Names

Lower-case letters, digits, hyphens and underscores, starting with a letter, at most 200 characters, as the user asked. The earlier pattern had no limit and no hyphens. A name becomes a folder name, a checkpoint repository `<name>.git` (204 characters, under the usual 255-byte limit), part of order tags (which keep only letters and digits and are cut to the broker's length) and a Telegram argument.

## Writing TOML

Python's `tomllib` reads TOML but cannot write it. Records hold only strings, integers, booleans and lists of strings, so `_toml_value` writes them with `json.dumps` for strings, whose escaping is valid TOML for basic strings. Each write goes through a `.toml.tmp` file and `replace`, so a crash never leaves half a record; `.gitignore` ignores those temporary files.
