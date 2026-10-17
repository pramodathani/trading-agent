# attachment_routes.py

Two routes: upload one file, and fetch one back.

## Why upload first, then send

The chat page uploads each file as soon as the user adds it, and sends the message later with the uploads' identifiers. Each file can then show its own progress and its own refusal ("not a type the desks can use") before the user presses Send, and the message itself stays a small JSON body. Telegram, which has the bytes in hand already, calls the store directly.

## Upload

`file.read(MAXIMUM_BYTES + 1)` reads at most one byte more than the limit, so a file far larger than 20 MB is not read fully into memory before being refused. A refusal answers 413 when the file was too large and 422 otherwise, with the store's explanation as the detail. Saving runs in a worker thread, because reading a long PDF's text can take a second or more and would otherwise hold up every other request and the desks.

## Fetch

The file is answered with its media type and `Content-Disposition: inline`, so a picture shows in the page and a PDF opens in the browser's viewer. The route needs the access token like every API route; the page therefore fetches files with the token in the header and shows them through `blob:` addresses, since an `<img src>` cannot send a header.
