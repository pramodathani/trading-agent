"""Reads the text of a PDF, page by page, with pypdf.

A scanned PDF holds pictures of pages and no text, so it reads as empty; the store then tells the trader so, and the user can send the pages as pictures instead.

Typical usage example:

  extracted = PdfTextReader().read(Path('annual_report.pdf'))
"""

from pathlib import Path

import pypdf
import pypdf.errors

from trading_agent.attachments import text_reader

_PYPDF_ERRORS = (
    pypdf.errors.PyPdfError,
    OSError,
    ValueError,
    KeyError,
)


class PdfTextReader(text_reader.TextReader):
    """Reads a PDF's text layer."""

    extensions = ('.pdf',)
    media_type = 'application/pdf'

    def read(self, path: Path) -> text_reader.ExtractedText:
        """Reads every page's text, each under a page heading.

        Args:
            path (Path): The PDF.

        Returns:
            text_reader.ExtractedText: The text and the number of pages.

        Raises:
            TextReadError: The file is damaged, is not a PDF, or needs a password.
        """
        reader = self._open(path)
        pages = []
        try:
            for number, page in enumerate(reader.pages, start=1):
                page_text = page.extract_text() or ''
                pages.append(f'--- Page {number} ---\n{page_text.strip()}')
        except _PYPDF_ERRORS as error:
            raise text_reader.TextReadError(
                f'the PDF cannot be read ({type(error).__name__}: {error})'
            ) from error
        return text_reader.ExtractedText(
            text='\n\n'.join(pages),
            page_count=len(pages),
        )

    def _open(self, path: Path) -> pypdf.PdfReader:
        """Opens the PDF, unlocking it when it is encrypted without a password.

        Args:
            path (Path): The PDF.

        Returns:
            pypdf.PdfReader: The open document.

        Raises:
            TextReadError: The file is damaged, is not a PDF, or needs a password.
        """
        try:
            reader = pypdf.PdfReader(path)
            locked = reader.is_encrypted and not reader.decrypt('')
        except _PYPDF_ERRORS as error:
            raise text_reader.TextReadError(
                f'the PDF cannot be read ({type(error).__name__}: {error})'
            ) from error
        if locked:
            raise text_reader.TextReadError(
                'the PDF is protected by a password'
            )
        return reader
