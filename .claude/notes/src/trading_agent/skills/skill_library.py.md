# skill_library.py

The library is what a desk sees of skills: the user's installed skills plus its own.

## Decisions

- **Index only in the prompt.** Each usable skill costs one line (name and description) in the system prompt; the full text arrives only through `load_skill`. With 40 skills that is about 40 lines rather than 40 documents, which matters for Gemma's and Qwen's 32,768-token window.
- **Hiding.** A skill whose programs (`shutil.which`) or environment variables are missing is hidden from the index and from `load_skill`, and `trading-agent skills list` says what each hidden skill needs. Variables are checked against what the bash sandbox actually receives (see `bash_sandbox.py`), not the gateway's environment, because the sandbox starts empty: a variable the gateway has would never reach the skill's script.
- **Name clashes.** An installed skill beats a desk skill of the same name, so a desk can never override the user's version. `skill_writer.py` also refuses to create such a name.
- **Read fresh every time.** No cache: a new import or a newly written skill shows up on the next turn. Reading a few dozen small files per turn is cheap next to a model call.
- **Fault tolerance.** One broken `SKILL.md` is logged and skipped. Folders starting with a dot (`.archive`, `.patch-check`) are never skills.

## Package skills (milestone 13, part 3)

Skills inside installed packages count as installed skills. On a name clash the user's own installed skill wins over a package's, and both win over the desk's own.
