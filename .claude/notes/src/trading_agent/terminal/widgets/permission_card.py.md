# permission_card.py

Tab moves to the reason box and back, and a letter typed while the choices have the focus goes into the reason box. Both came from a live test on 2026-10-18 on the scratch gateway: Tab did not leave the choices, the typed reason was dropped, and the following Enter picked the highlighted "Yes", allowing `flatten_trader` in dry run on a flat trader, so nothing was sent. The reason box is created with `select_on_focus=False`, because Textual's `Input` selects its text when it gains the focus and the next key would replace the first letter.

A lapsed request is not sent; the gateway has already told the trader no.
