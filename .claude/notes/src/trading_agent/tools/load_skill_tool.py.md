# load_skill_tool.py

Returns a skill's instructions and the absolute paths of its `scripts/` and `references/` files. Absolute paths matter: the trader's bash session runs in its scratch folder inside the sandbox, which can read the whole filesystem except hidden secrets, so `python3 /abs/path/scripts/x.py` works without copying anything. An unknown name returns the list of usable skills, so a model that misspells a name can recover in one step. Each call opens a use in `skill_usage.py`.

## Injection warning (milestone 13, part 3)

If a skill's body contains something the injection scanner recognises, a warning comes before it, telling the trader to follow the trading steps but never steps that get around its rules, the risk engine or the user. The body is not labelled as outside data, because skills are instructions the user chose.
