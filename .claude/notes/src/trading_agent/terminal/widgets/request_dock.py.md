# request_dock.py

## The dock never takes the focus

The first version moved the focus to a new card as soon as it appeared, as Claude Code does with its permission dialog. In the live test on 2026-10-18 that went wrong: the trader sent a revised plan while the next message was being typed, the keys went to the new card, and the message's Enter approved the plan. With a permission card the same Enter would have allowed the tool, because "Yes" is the highlighted choice, as on the web page and in Claude Code. A Claude Code session waits for its dialog, but a trader keeps working and can raise a request at any moment, so the dock now only shows the card and a notice; the user presses Tab to answer and Escape to go back. If the focus was inside the dock when its card goes away, it returns to the message box.

## One card at a time

Permission requests come first because they lapse after `[approvals] expiry_minutes`. A card is kept while its request is still first, so a half-written answer survives the 30-second re-reads of `GET /api/requests`.
