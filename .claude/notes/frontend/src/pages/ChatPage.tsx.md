# ChatPage.tsx

The page reads today's journal for the chosen trader and adds live events. Enter sends; Shift and Enter starts a new line. Typing `/` offers the slash commands.

A message sent while the trader is working is steering: the running turn takes it at its next tool call, and the message is drawn inside that turn at the point it arrived, with its status (waiting, handed over, or queued as the next turn when the turn ended first). The Stop button appears while the trader is busy and sends /stop.

The text a turn is writing appears as it streams, in a dashed "Writing…" bubble, and is replaced by the final answer. Every backend already streamed its text in milestone 3 and later; part 1 of milestone 18 wrongly said they did not, because a search for the delta events was cut short. Streamed text is live only: the journal does not keep it, so a reloaded page shows final answers.

A stopped turn's partial text is not kept; the turn shows "Stopped by the user" instead. Stopped turns are not saved as exchanges in the session, because only finished turns are.

Tested in Chrome on 2026-10-17 with the scalper trader on Qwen: a message sent during a four-call task was handed over and Qwen ended its answer with the requested word; Stop ended a 700-word essay mid-stream, and the next message was answered normally.

Answers are shown as plain text with line breaks kept, not rendered Markdown, to avoid another dependency for now.

## Attachments, since 2026-10-17

Files can be added three ways: the Attach button (a hidden file input), dropping files on the message box, and pasting a picture into it, which covers screenshots copied to the clipboard. Each file is uploaded at once and shown as a chip: uploading, ready, or not attached with the reason. Send waits until no file is still uploading, and sends the ready ones' identifiers with the text; the text may be empty when files are attached.

The chips are cleared when the user switches trader, because an upload belongs to one trader and cannot be sent to another. Picture previews in the chips use `blob:` addresses of the local file, revoked when the chip goes.

In the history, the user's bubble shows its attachments through `AttachmentList`, and the text block is left out when a message was only files.

## Pictures from the trader

A tool card's picture is drawn below the folded card, not inside it, because a screenshot hidden behind a click is easy to miss. A `message` event, whether inside a turn or loose, is drawn by `TraderMessageView` as a trader bubble with its text and pictures; before part 2 a message inside a turn showed only the word "Message", hiding its text.

## States in words

The trader's state is put into words by `traderStateWords`, and only busy and waiting count as working, so a sleeping trader is not shown as busy.
