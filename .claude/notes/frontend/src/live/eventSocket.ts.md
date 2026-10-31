# eventSocket.ts

There is one WebSocket for the whole page, not one per page, so switching pages does not drop events and the gateway keeps one subscription per browser tab. It subscribes to every trader; pages filter in the browser, because the Traders and Activity pages need all of them anyway.

The last 3000 events are kept in memory, enough for a busy day's live view without growing without bound. Each new event replaces the array rather than changing it, so React's `useSyncExternalStore` sees a new value and re-renders.

When the connection drops, it is reopened after 1 second, then 2, 4 and so on up to 15 seconds, so a restarting gateway is not flooded with attempts. A close with code 1008 means the token was refused, so it clears the token instead of retrying.

Events that happen while the connection is down are not replayed. The Chat and Activity pages read the journal when they open, which covers that gap on the next visit.

## Streamed text (milestone 18, part 2)

Streamed text arrives as one `text_delta` event per small piece, often hundreds per answer. Keeping each as an event would push important events out of the 3000-event memory, so the socket joins the pieces per trigger into `streamingTexts()` instead, and drops a turn's entry when its final text or a tool call arrives.
