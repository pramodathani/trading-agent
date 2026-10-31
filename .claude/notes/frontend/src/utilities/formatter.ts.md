# formatter.ts

One place for how numbers, money and times are written on the page, so every page writes them alike.

`fileSize`, added on 2026-10-17 for attachments, writes sizes under one megabyte in whole kilobytes (never less than 1 KB) and larger ones in megabytes with one decimal, the same rule as `Attachment._readable_size` in Python, so the size the page shows matches the size in the trader's note.
