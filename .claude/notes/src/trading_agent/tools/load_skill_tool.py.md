# load_skill_tool.py

Returns a skill's instructions and the absolute paths of its `scripts/` and `references/` files. Absolute paths matter: the desk's bash session runs in its scratch folder inside the sandbox, which can read the whole filesystem except hidden secrets, so `python3 /abs/path/scripts/x.py` works without copying anything. An unknown name returns the list of usable skills, so a model that misspells a name can recover in one step. Each call opens a use in `skill_usage.py`.
