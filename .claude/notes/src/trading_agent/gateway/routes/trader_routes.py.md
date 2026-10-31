# trader_routes.py

Rewritten in milestone 17 on the shared `RouteGroup` base. It answers each trader's state, models and session, and adds the persona, pause, resume and flatten.

Flatten deliberately runs the trader's own `flatten_trader` tool rather than calling UBI directly. That way the user's flatten goes through exactly the same path as the trader's own: the risk engine, the trader's tag, the order book and the journal. The reason is prefixed with "From the user, through the API" so the journal shows who asked.

`preferred_model` is empty until someone chooses a model with `/model`; until then the trader follows its configured order, which `models` lists. The live test on 2026-10-17 showed all four traders with an empty preferred model for this reason.

The parts, layout and mode are optional so the old two-argument form still works; the gateway uses that form when it is given no route groups, which keeps the earlier gateway tests unchanged.

## Attachments on messages, since 2026-10-17

`MessageRequest.text` may now be empty when `attachment_ids` names at least one upload; a message with neither is refused with 422 by the model validator. At most ten files go with one message.

Each identifier is looked up in the trader's own uploads, so a message cannot attach another trader's file. An unknown identifier answers 422 rather than 404, because the route was found and it is the request's content that is wrong.

## GET /api/traders/{trader}/commands

Added on 2026-10-18 for the terminal program and the web page's slash menu. It is per trader because each trader has its own usable skills. The answer comes from `TraderRuntime.command_catalogue()`, which reads the skill library from disk; like the other sync routes it runs in a worker thread, and it only reads.
