# PictureThumbnail.tsx

Pictures cannot be loaded with a plain `<img src>`, because every API route needs the access token in the `Authorization` header and an image request cannot send one. The component fetches the picture with the token, turns it into an object URL, and revokes that URL when it unmounts, so a long chat does not keep every picture in memory.

It takes a `load` function and a `loadKey` rather than a URL, so the same component serves uploaded attachments (`apiClient.attachmentFile`) and trader-folder pictures in tool cards (`apiClient.traderPicture`). The effect depends on `loadKey` only: `load` is a new function on every render, and depending on it would fetch the picture again each time the chat redraws.
