# text_reader.py

The base of the four document readers. Following the project's rule that each case gets its own self-contained class, PDF, Word, Excel and plain text each have a reader in their own file; the base holds only what is genuinely the same: the list of file endings a reader takes, its media type, and the `read` contract.

`TextReadError` is a `ValueError` so callers that only care that the input was bad can catch it broadly; the store catches it specifically and keeps the document with the reason.

`ExtractedText.page_count` is set only by formats that have pages (PDF), so the trader's note can say "12 pages".
