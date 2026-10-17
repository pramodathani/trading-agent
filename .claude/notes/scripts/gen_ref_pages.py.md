# scripts/gen_ref_pages.py

A simpler version of tradingmachine's generator: one page per module, the module as the title and each public class as a section in source order. tradingmachine's class hierarchy page and example programs are left out, because trading-agent has no examples folder and its classes are mostly flat. It reads the source with `ast` and never imports the package, so the site builds without the project's dependencies, as the GitHub workflow does.

An empty `__init__.py` gets no page, so a link to a package's index only works for packages whose `__init__.py` has a docstring, such as `trading_agent` itself.
