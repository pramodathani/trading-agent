# ChatPage.tsx

The page reads today's journal for the chosen desk and adds live events. Enter sends; Shift and Enter starts a new line. Typing `/` offers the slash commands.

A message sent while the desk is busy waits in its queue until the current turn ends; the page says so. Steering a running turn and `/stop` were deferred when slash commands were built, and text does not stream word by word yet because no backend publishes text deltas. Both are planned for part 2 of milestone 18.

Answers are shown as plain text with line breaks kept, not rendered Markdown, to avoid another dependency for now.
