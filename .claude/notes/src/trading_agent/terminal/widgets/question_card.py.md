# question_card.py

The rules copy `QuestionCard.tsx`: a single question with a single choice is sent as soon as an option is picked; several questions get a tab each and a review tab, and Submit needs every question answered. The card itself can take the focus, because the review tab has no option list, and without a focused widget inside the card its Ctrl+S binding never fired.

In screenshots converted with rsvg-convert, a space after bold text can look missing ("generalasks"). The text is right; rsvg draws the bold glyphs wider. The real terminal shows the space.
