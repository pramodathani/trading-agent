# chat_transcript.py

This is a port of `frontend/src/utilities/chatTurnBuilder.ts` plus the streaming part of `frontend/src/live/eventSocket.ts`, so the terminal and the browser show a turn the same way. Keep the two in step: a rule changed in one should be changed in the other.

The web page rebuilds the whole chat from every event on each render. The terminal is fed one event at a time instead, and `add()` returns the item that changed, so a Textual screen redraws one turn rather than the whole transcript. Three consequences follow from that:

- A steering message lives inside the running turn's `SteeringStep`, so a change to it returns the running turn (`_shown_item`), because that is what is on screen.
- `text_delta` is kept on the turn as `streaming_text`, cleared by `text` and `tool_call`, which is when the web page drops its stream buffer.
- Events read from the journal and received live are both added; `key()` (the same key as `eventMerger.ts`) drops the second copy. Text deltas are never journaled, so they skip the check.

`user_request` events carry no `trigger_id`. As on the web page, a request joins the turn that is open when it arrives.
