# AttachmentList.tsx

Shows the pictures and documents sent with a message, inside the user's bubble in Chat.

Every API request needs the access token in the `Authorization` header, and an `<img src>` cannot send one. Each picture is therefore fetched with `apiClient.attachmentFile`, turned into a `blob:` address with `URL.createObjectURL`, and the address is revoked when the picture leaves the page, so memory is returned.

A document opens in a new tab the same way. The tab is opened before the fetch, while the click still counts as the user's action; a tab opened after an `await` is blocked as a pop-up by most browsers.

A document whose text could not be read says "text not readable", and its title gives the reason, so the user knows why the desk could not use it.
