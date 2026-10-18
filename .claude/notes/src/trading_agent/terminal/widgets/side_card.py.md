# side_card.py

A shallow base class: it holds only what every card does identically (a foldable body, a title note, rows of a label and a right-aligned value). Each card's own logic stays in its own file, as the project's style asks.

Screenshots: Textual's SVG export does not mark its text `xml:space="preserve"`, so `rsvg-convert` collapses runs of spaces and right-aligned values look left-aligned. Add the attribute to the `<svg>` element before converting.
