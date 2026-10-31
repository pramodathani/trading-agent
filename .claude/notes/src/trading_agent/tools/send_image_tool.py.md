# send_image_tool.py

## Why it exists

Before this tool a trader could make a picture, for example by rendering HTML with headless Chrome, but had no way to show it; on 17 October 2026 the main trader answered "I made the image, but I can't show it to you here." `send_message` carries text only.

## Copying into uploads

The picture is copied into the trader's uploads folder through `AttachmentStore.save`, the same store that keeps the user's uploads. That gives four things without new code: the picture is checked as a real PNG, JPEG, WebP or GIF by its contents; it is kept after `scratch/` is cleared, so the chat history still shows it; the existing `GET /api/traders/{trader}/attachments/{id}` route serves it to the web page; and the event carries the same attachment dictionary that user messages carry, so the page draws it with the same `AttachmentList`.

The file's ending is checked before saving, because the store would accept a PDF or CSV as a document and the trader would then be told the user saw a picture.

## The event

It publishes a `message` event, like `send_message`, with `urgent` false and an `attachments` list. Reusing the kind means the journal, the activity feed and the Telegram formatter already know it. The event has no `trigger_id` because tools are not told their trigger; the web page places it in the open turn, and the Telegram channel finds the turn from the trader's running trigger.

The result tells the model not to describe the picture again, because models otherwise repeat in words what the user can now see.
