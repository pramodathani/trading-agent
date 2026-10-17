# Writing these docs

This site is built with MkDocs and the Material theme, configured like the tradingmachine and UBI sites. Its hand-written pages live in `docs/`, and its API reference is generated from the docstrings in `src/trading_agent` every time the site is built.

## Previewing and building

The toolchain is the `docs` extra in `pyproject.toml`:

```bash
.venv/bin/pip install -e ".[docs]"
.venv/bin/mkdocs serve -a 127.0.0.1:8130     # live preview, rebuilt on every save
.venv/bin/mkdocs build --strict               # the full build, failing on any warning
```

The preview uses port 8130 so that it never clashes with the gateway on 8120. Always finish with `mkdocs build --strict`: a broken link, a page missing from the nav or a missing diagram stops the build.

## Publishing

`.github/workflows/docs.yml` builds the site with `mkdocs build --strict` on every push and pull request, and publishes it to GitHub Pages from `main`, exactly as for tradingmachine. It installs only the packages in the `docs` extra, read from `pyproject.toml`. The repository does not have a GitHub remote yet, so the site is not published until one exists.

## Diagrams

The animated diagrams are SVG files in `docs/assets/diagrams/`, included into pages with the snippets syntax inside a `figure` with the class `diagram`:

```html
<figure class="diagram">
--8<-- "docs/assets/diagrams/desks.svg"
<figcaption>What the dots mean.</figcaption>
</figure>
```

Each SVG has the class `ta-svg` and no colours of its own: boxes, wires, text and dots take their colours from `docs/stylesheets/extra.css`, which defines them for the light and the dark theme. Every `id` in a diagram starts with the diagram's name, so two diagrams on one page never share an animation path. The diagrams began as the milestone diagrams of the build and were converted to this form.

## The API reference

`scripts/gen_ref_pages.py` writes one page per module of `src/trading_agent` while the site builds, nothing on disk: the module as the title, then each public class in source order with its methods. Its navigation goes to `reference/SUMMARY.md` for the literate-nav plugin, which is why `mkdocs.yml` says only `- API reference: reference/`.
