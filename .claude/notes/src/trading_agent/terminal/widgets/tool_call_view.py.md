# tool_call_view.py

The card passes its body to `Collapsible.__init__` instead of overriding `compose()`, because `Collapsible.compose()` is what draws the title row; the first version overrode it and lost the title. The title method is `_title_content`, not `_title`, because `Collapsible` keeps its title widget in `self._title`.

Separators in the title are ` · ` rather than double spaces, which the title row collapses.
