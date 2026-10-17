# pdf_text_reader.py

Uses pypdf 6.21.1, which is pure Python and needs no system libraries.

Each page's text goes under a `--- Page N ---` heading so the desk can say where in the document something is, and so `AttachmentStore._has_words` can tell a scanned PDF (headings only) from one with text.

## Encrypted PDFs

Many bank and broker statements are "encrypted" with an empty user password, only to stop editing. `decrypt('')` opens those. A PDF that needs a real password is refused with that reason; the desk then asks the user, rather than the gateway asking for passwords.

## Scanned PDFs

A scan is pictures of pages with no text layer, so it reads as headings only, and the store reports that the user should send the pages as pictures. Rendering pages to pictures would need a renderer such as pdfium or poppler; that was left out of the first version to keep the dependencies small.

The tuple of caught errors includes `KeyError` and `ValueError` because pypdf raises them, not only `PyPdfError`, on some damaged files.
