# apiClient.ts

One method per API route the pages use. Errors become `ApiError` with FastAPI's `detail` text, so pages can show the gateway's own explanation, such as the reason a TradingRules.md was refused.

`allJournals` reads every trader's journal and the gateway's own, then sorts the events by time, because the API has one journal per trader. The Activity page uses it to show the whole day on first load.

## Attachments, since 2026-10-17

`uploadAttachment` sends a `FormData` body; `request` leaves the `Content-Type` header unset for it, so the browser writes the multipart boundary itself. `attachmentFile` fetches a stored file with the token, for pictures and documents shown through `blob:` addresses. `sendMessage` takes the attachment identifiers.

`traderPicture` encodes each part of the path separately, so the slashes between folders stay as they are while spaces and other characters in file names are escaped.
