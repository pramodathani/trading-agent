# broker_reader.py

All reading from UBI goes through this one object, shared by every desk, so its lock lets one UBI call run at a time across the whole gateway, as the tradingmachine_mcp server does with its ToolGuard. tradingmachine is synchronous, so each call runs in a worker thread with `asyncio.to_thread`; the desks keep working while UBI answers.

The client is built explicitly from `tradingmachine_environment_file` in trading_agent.toml. tradingmachine's default Configuration searches the working folder and its parents for a `.env`, which from trading-agent's folder finds trading-agent's own `.env`, with no UBI settings; tradingmachine's CLAUDE.md warns about exactly this. Every Instrument is built with that client, and as a plain `Instrument`, which has no order methods, so no read tool can place an order even by mistake.

Loading the `.env` copies tradingmachine's settings, including database passwords, into the gateway's environment (`dotenv.load_dotenv`). The bash sandbox clears its environment, and the Claude runner blanks every `TRADINGMACHINE_` variable for Claude Code; verified on 2026-10-17, when a Claude Code process started after the settings were loaded held all 16 of them empty.
