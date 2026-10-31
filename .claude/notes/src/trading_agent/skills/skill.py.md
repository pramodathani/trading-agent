# skill.py

Skills (block 23) use the open Agent Skills format: a folder with `SKILL.md`, YAML frontmatter between `---` lines, then Markdown. Claude Code, Hermes and others share it, so skills can move between them.

## Decisions

- **Name rule**: 1 to 64 lower-case letters, digits and hyphens, starting with a letter or digit, which is the format's own rule. The name doubles as the folder name and as the `/<skill-name>` command, so it must be safe in both places.
- **Two ways to declare needs**: the plan's `requires: {programs, environment}`, and Hermes's `prerequisites: {commands, env_vars}`. On this machine 11 Hermes skills declare `commands` and 4 declare `env_vars`, so reading Hermes's spelling lets them be imported unchanged. Other frontmatter keys, such as `version`, `metadata` or `platforms`, are ignored.
- **YAML**: `yaml.safe_load`, never `yaml.load`, because imported frontmatter is untrusted and full YAML can build arbitrary Python objects. PyYAML was already installed as a dependency of another package; it is now declared in `pyproject.toml` because skills depend on it directly.
- `frontmatter_text` writes frontmatter for skills the trader creates, through `yaml.safe_dump`, so a description with a colon or quote is quoted correctly.
- `bundled_files` lists `scripts/` and `references/` so `load_skill` can give the trader absolute paths to read or run.
