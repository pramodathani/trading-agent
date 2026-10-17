# ChatPage.tsx

The page reads today's journal for the chosen desk and adds live events. Enter sends; Shift and Enter starts a new line. Typing `/` offers the slash commands.

A message sent while the desk is working is steering: the running turn takes it at its next tool call, and the message is drawn inside that turn at the point it arrived, with its status (waiting, handed over, or queued as the next turn when the turn ended first). The Stop button appears while the desk is busy and sends /stop.

The text a turn is writing appears as it streams, in a dashed "Writing…" bubble, and is replaced by the final answer. Every backend already streamed its text in milestone 3 and later; part 1 of milestone 18 wrongly said they did not, because a search for the delta events was cut short. Streamed text is live only: the journal does not keep it, so a reloaded page shows final answers.

A stopped turn's partial text is not kept; the turn shows "Stopped by the user" instead. Stopped turns are not saved as exchanges in the session, because only finished turns are.

Tested in Chrome on 2026-10-17 with the scalper desk on Qwen: a message sent during a four-call task was handed over and Qwen ended its answer with the requested word; Stop ended a 700-word essay mid-stream, and the next message was answered normally.

Answers are shown as plain text with line breaks kept, not rendered Markdown, to avoid another dependency for now.
