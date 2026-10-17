# source_fetcher.py

Moved out of `skill_importer.py` when packages needed the same three sources. It is the genuinely identical part of both; the importer and the installer keep their own logic for what to do with the fetched folder. The zip check refuses any entry that would land outside the unpacking folder, and git clones only the latest commit.
