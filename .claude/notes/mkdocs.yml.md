# mkdocs.yml

The documentation site is configured like the tradingmachine and UBI sites, with the same theme, palette (deep orange, light, dark and follow-the-system), features, Markdown extensions and plugins, so the three sites look and behave alike. The pinned versions are the `docs` extra in pyproject.toml, the same versions tradingmachine pins.

`site_url` and `repo_url` name a GitHub repository, pramodathani/trading-agent, that did not exist when the site was built on 2026-10-17; they are what the published site will use once the repository exists.

The two guides that code refers to by path, docs/telegram_setup.md and docs/going_live.md, stay at those paths and are placed in the Using it tab by the nav, so the doctor's messages still point at real files.

## Why `navigation.instant` is off, since 2026-10-17

Material's instant loading was switched off because it stopped page changes from working on any page with an animated diagram. The user noticed that clicking a link often changed the address bar but left the old page showing until a refresh.

With `navigation.instant`, Material fetches the next page in the background and swaps in its content. Before swapping, it rewrites every element that has an `href` or `src` attribute with the equivalent of `element.href = element.href`. The animated diagrams are inlined into the pages, and each moving dot holds an `<mpath href="#wire">`. On `SVGMPathElement`, `href` is a read-only `SVGAnimatedString`, so the assignment throws `TypeError: Cannot set property href of #<SVGMPathElement> which has only a getter`. The exception ends Material's navigation stream for the rest of the visit. Later clicks still push the new address, but nothing fetches or swaps the page. A refresh is an ordinary full load, which is why it worked.

Writing the dots as `<mpath xlink:href=...>` also avoids the error, because Material's selector is `[href], [src]`, and this was checked in Chrome on 2026-10-17. It was not chosen, because every future diagram would have to remember the older spelling, and `~/.claude/tools/svg_to_gif.py` only recognises `<mpath href=`. Without instant loading, every link is an ordinary page load, which is barely slower for a static site, and `navigation.tracking` and `toc.follow` keep working.
