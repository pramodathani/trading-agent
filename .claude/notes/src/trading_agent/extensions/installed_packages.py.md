# installed_packages.py

Packages (block 27) are read in place: the skill library, the hook runner and the MCP configuration reader each ask this class for the relevant parts of every installed package. Removing a package is therefore deleting its folder, with no list of copied files to keep in step.

`agents/` is listed now but used from milestone 14 (subagents); `app.toml` is listed now but used from milestone 20 (packages as apps). A package with an unreadable package.toml still works; it just has no description or version.

Since milestone 20, app.toml is read by app_catalog.py; installed packages are machine state and are kept out of git, while package sources such as packages/sridhara are committed.
