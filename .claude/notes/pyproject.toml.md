# pyproject.toml

The project name is `trading-agent` with a hyphen, while the import package is `trading_agent` with an underscore. pip treats the two spellings as the same project name, but Python cannot import a name containing a hyphen, because `import trading-agent` parses as a subtraction. The Google style guide also forbids dashes in module names.

Dependencies are pinned to exact versions, matching the versions sridhara uses, so that the sibling projects share one known-good set and an upgrade is always a deliberate change. pytest and ruff are in a `development` extra so a production install does not need them.

The build uses hatchling, as `tradingmachine` and `tradingmachine_mcp` do, with the package under `src/` so that tests import the installed package rather than a folder that happens to be on the path.

`tradingmachine` is not listed as a dependency because it is not published anywhere; it is installed separately with `pip install -e ../tradingmachine`, which keeps changes in that project visible here immediately.

## Attachment packages, since 2026-10-17

- `pypdf==6.21.1`, `python-docx==1.2.0` and `openpyxl==3.1.5` read PDF, Word and Excel documents. All three are pure Python.
- `pillow==12.3.0` checks and resizes pictures. It was already installed as a dependency of another package; it is pinned now that trading-agent imports it itself.
- `python-multipart==0.0.32` is what FastAPI needs to read uploaded files; it was also already installed.
