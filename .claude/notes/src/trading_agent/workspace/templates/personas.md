# templates/personas/

Starter personas for the plan's three traders, written into `workspace/traders/<trader>/Persona.md` when a trader with that name is first created; any other trader gets the general Persona.md template. Once written they belong to the user, who edits them.

| Trader | Product | Holding | Routine (the trader's scheduled_checks) |
|---|---|---|---|
| intraday | `mis` | minutes to hours, flat by 15:15 | 09:05 plan, 15:05 flatten, 15:35 review; heartbeat every 10 minutes |
| scalper | `mis` | seconds to minutes, flat by 15:15 | 09:10 pick instruments, 15:05 flatten; heartbeat every 2 minutes on Qwen |
| positional | `cnc`, `nrml` | days to weeks | 08:45 pre-market with news_reader, 12:30 mid-day, 15:40 after-close plan; no heartbeat |

Each says the trader must watch and report, not open positions, until a strategy for it is written in TradingRules.md. The scalper's describes the plan's two layers: the model decides, UBI's bracket orders execute.
