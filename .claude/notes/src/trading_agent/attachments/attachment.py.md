# attachment.py

An `Attachment` is the record of one upload that travels with a message: in the trigger, in the `trigger_received` event (so the chat page can redraw the picture after a reload), and in `attachment.json` next to the file. It never carries the file's bytes; the file stays on disk and is read when a model turn needs it.

## Two kinds, two treatments

- **Pictures** are shown to the model with the message. All three backends take pictures, and both local models (`gemma4:31b`, `qwen3.8:27b`) list `vision` among their Ollama capabilities, checked on 2026-10-17.
- **Documents** are never put into the message whole. Their text is read once on arrival into `text.txt`, and the message carries a one-line note saying where that text is, so the desk reads it with `read_file`, a page at a time. A 40-page PDF would otherwise fill most of a local model's 32,768-token context in one message.

## `describe_for_model`

The note is one bracketed line, in the same style as the turn's first line (`[India time: ...]`), so the model reads it as a fact about the message rather than as the user's words. It gives the path relative to the desk folder because that is what `read_file` takes. When a document's text could not be read, the note says why, so the desk can tell the user instead of guessing.

## Two paths

`path` is absolute, for the code that opens the file. `desk_path` is relative to the desk folder, for the model and for moving the workspace: `AttachmentStore.find` rebuilds `path` from `desk_path`, so a workspace copied elsewhere still finds its uploads.
