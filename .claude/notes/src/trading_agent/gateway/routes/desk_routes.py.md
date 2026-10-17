# desk_routes.py

Rewritten in milestone 17 on the shared `RouteGroup` base. It answers each desk's state, models and session, and adds the persona, pause, resume and flatten.

Flatten deliberately runs the desk's own `flatten_desk` tool rather than calling UBI directly. That way the user's flatten goes through exactly the same path as the desk's own: the risk engine, the desk's tag, the order book and the journal. The reason is prefixed with "From the user, through the API" so the journal shows who asked.

`preferred_model` is empty until someone chooses a model with `/model`; until then the desk follows its configured order, which `models` lists. The live test on 2026-10-17 showed all four desks with an empty preferred model for this reason.

The parts, layout and mode are optional so the old two-argument form still works; the gateway uses that form when it is given no route groups, which keeps the earlier gateway tests unchanged.
