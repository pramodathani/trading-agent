# eventSocket.ts

There is one WebSocket for the whole page, not one per page, so switching pages does not drop events and the gateway keeps one subscription per browser tab. It subscribes to every desk; pages filter in the browser, because the Desks and Activity pages need all of them anyway.

The last 3000 events are kept in memory, enough for a busy day's live view without growing without bound. Each new event replaces the array rather than changing it, so React's `useSyncExternalStore` sees a new value and re-renders.

When the connection drops, it is reopened after 1 second, then 2, 4 and so on up to 15 seconds, so a restarting gateway is not flooded with attempts. A close with code 1008 means the token was refused, so it clears the token instead of retrying.

Events that happen while the connection is down are not replayed. The Chat and Activity pages read the journal when they open, which covers that gap on the next visit.
