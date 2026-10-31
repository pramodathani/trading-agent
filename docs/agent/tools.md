# Tools

A trader acts through tools. Each tool is a class with a JSON schema, and the same tools are offered to every model. The table below lists all 49, grouped by what they are for. A trader whose trader.toml sets `jev_signals` also gets a 50th, `jev_decision`, which asks [Jev](models.md#jev-a-decision-model) whether NIFTY is a buy, a sell or a hold.

| Group | Tools |
|---|---|
| Market data | `get_time`, `get_quote`, `get_candles`, `search_instruments` |
| The account | `get_portfolio`, `get_orders` |
| Orders | `place_order`, `place_bracket_order`, `modify_order`, `cancel_order`, `flatten_trader` |
| Terminal | `bash_run`, `bash_background`, `bash_check`, `bash_restart` |
| Browser | `browser_open`, `browser_snapshot`, `browser_click`, `browser_type`, `browser_screenshot`, `browser_back`, `browser_tabs` |
| The web | `web_search`, `web_fetch` |
| Files and memory | `read_file`, `write_file`, `edit_file`, `add_note`, `search_sessions`, `propose_file_change` |
| Pictures | `view_image`, `send_image` |
| Skills | `load_skill`, `skill_create`, `skill_patch`, `skill_archive` |
| Scheduling and messages | `cron_create`, `cron_list`, `cron_delete`, `schedule_wakeup`, `set_price_alert`, `cancel_price_alert`, `send_message` |
| Asking you | `ask_user`, `present_plan` |
| Extensions | `tool_search`, `call_mcp_tool`, `delegate_task`, `search_knowledge` |

The full description each model reads is in the API reference, one page per tool, such as [place_order](../reference/trading_agent/tools/place_order_tool.md). A tool call that runs longer than 60 seconds is stopped, and the loop guard stops a tool called three times with the same arguments in one turn. A tool listed in `[approvals]`, which is only `flatten_trader` on this machine, is held until you allow it, as [Questions, plans and permissions](../using/questions-and-permissions.md#permission-prompts) explains.

## The terminal

Each trader has one bash session that keeps running between commands, so the current folder and variables carry over. It runs inside **bwrap**, a sandbox: the trader's `scratch/` folder and `/tmp` are the only places it may write, the project and your files are read-only, and the folders that hold secrets appear empty.

<figure class="diagram">
--8<-- "docs/assets/diagrams/bash-sandbox.svg"
<figcaption>What the trader's bash session can reach. It may write only in its scratch folder; the project is read-only; credential folders and every .env appear empty; the network is open so it can fetch data.</figcaption>
</figure>

The sandbox starts with an empty environment, so no secret reaches it unless `[sandbox] passed_environment` names it.

## The browser

Each trader has its own headless Chrome with a clean profile, never your own, because your profile holds your broker logins. A page comes back as a snapshot: its title, its clickable elements numbered so the model can click by number, and its visible text. The models can also take a screenshot and look at it, and Chat shows it under the tool's card. [Pictures and documents](../using/pictures-and-documents.md) explains `view_image` and `send_image`.

<figure class="diagram">
--8<-- "docs/assets/diagrams/browser.svg"
<figcaption>The browser tools. A request guard blocks local addresses, so a page cannot reach UBI or the gateway through the trader's browser; what comes back is numbered elements and text, or a screenshot.</figcaption>
</figure>

## Web search and fetch

`web_search` asks the local SearXNG server, and `web_fetch` turns one page into its main text with its title and date. Both are far cheaper than the browser for reading news. `web_fetch` and the browser share the address guard: every address a host name resolves to must be a public internet address, checked again at each redirect, so a page cannot steer a trader to UBI, the databases or a router on the home network. Text from the web is labelled as untrusted data before the model reads it, as [Extensions](extensions.md#untrusted-text) explains.

## The journal

Every tool call, result, order, risk decision and fill is written to the trader's journal, one file per day, after secrets are masked. The Activity page reads it, and so does `search_sessions`.

<figure class="diagram">
--8<-- "docs/assets/diagrams/read-and-journal.svg"
<figcaption>The broker reader reads UBI for the trader; every event passes through the secret redactor before the journal writes it and the live stream sends it.</figcaption>
</figure>
