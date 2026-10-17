# .github/workflows/docs.yml

Copied unchanged from tradingmachine: it builds the site strictly on every push and pull request and publishes it to GitHub Pages from main. It installs only the `docs` extra, read from pyproject.toml, so no model, UBI or secret is needed to build the site. It does nothing until the project has a GitHub repository.
