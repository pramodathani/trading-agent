"""The base of the classes that turn one kind of document into plain text.

Each document format has its own reader in its own file: PDF, Word, Excel, and plain text such as CSV, Markdown and JSON. They share only this base, which says which file endings a reader takes and what it returns.

Typical usage example:

  extracted = PdfTextReader().read(Path('report.pdf'))
"""

import abc
import dataclasses
from pathlib import Path


class TextReadError(ValueError):
    """A document could not be read as text."""


@dataclasses.dataclass(frozen=True)
class ExtractedText:
    """The text read from one document.

    Attributes:
        text: The document's text.
        page_count: How many pages it has, for formats with pages, or None.
    """

    text: str
    page_count: int | None = None


class TextReader(abc.ABC):
    """Reads documents of one format.

    Attributes:
        extensions: The lower-case file endings this reader takes, such as ".pdf".
        media_type: The media type of those files, used when the sender gave none.
    """

    extensions: tuple[str, ...] = ()
    media_type = 'application/octet-stream'

    def takes(self, file_name: str) -> bool:
        """Says whether this reader reads a file of this name.

        Args:
            file_name (str): The file's name.

        Returns:
            bool: True when the name ends with one of the reader's endings.
        """
        return Path(file_name).suffix.lower() in self.extensions

    @abc.abstractmethod
    def read(self, path: Path) -> ExtractedText:
        """Reads a document's text.

        Args:
            path (Path): The document.

        Returns:
            ExtractedText: Its text.

        Raises:
            TextReadError: The file is damaged, protected or not of this format.
        """
