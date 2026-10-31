"""One file the user sent with a message: a picture or a document.

The file itself stays in the trader's uploads folder. An attachment is what travels with the message and is written into events: the file's name, type and size, where it is stored, and for a document, where its text is and how long it is.

Typical usage example:

  note = attachment.describe_for_model()
  dictionary = attachment.to_json_dictionary()
"""

import dataclasses
import enum
from pathlib import Path
from typing import Any, Self


class AttachmentKind(enum.StrEnum):
    """What sort of file an attachment is."""

    IMAGE = 'image'
    DOCUMENT = 'document'


@dataclasses.dataclass(frozen=True)
class Attachment:
    """One stored upload.

    Attributes:
        attachment_id: A unique identifier, also the name of the folder the upload is stored in.
        trader: The trader it was sent to.
        kind: A picture, which the model looks at, or a document, which the model reads as text.
        file_name: The file's name as the user sent it.
        media_type: The file's media type, such as image/png or application/pdf.
        size_bytes: The file's size.
        path: The stored file, as an absolute path.
        trader_path: The stored file relative to the trader folder, as the trader's tools take it.
        text_trader_path: For a document whose text was read, that text file relative to the trader folder, otherwise None.
        text_characters: How many characters of text the document holds, or None.
        page_count: How many pages a PDF has, or None for other files.
        problem: Why a document's text could not be read, or an empty string.
        created_at: When it was stored, as an ISO 8601 string in UTC.
    """

    attachment_id: str
    trader: str
    kind: AttachmentKind
    file_name: str
    media_type: str
    size_bytes: int
    path: str
    trader_path: str
    text_trader_path: str | None
    text_characters: int | None
    page_count: int | None
    problem: str
    created_at: str

    @property
    def is_image(self) -> bool:
        """Whether the attachment is a picture."""
        return self.kind == AttachmentKind.IMAGE

    def describe_for_model(self) -> str:
        """The note the trader reads about this attachment in the message.

        Returns:
            str: One bracketed line saying what was attached and how to use it.
        """
        size = self._readable_size()
        if self.is_image:
            return f'[Picture attached: {self.file_name} ({size}), saved at {self.trader_path}. It is shown to you with this message.]'
        if self.text_trader_path is None:
            return f'[Document attached: {self.file_name} ({size}), saved at {self.trader_path}. Its text could not be read: {self.problem}]'
        length = f'{self.text_characters:,} characters'
        if self.page_count is not None:
            length = f'{self.page_count} pages, {length}'
        return f'[Document attached: {self.file_name} ({size}; {length}). Its text is at {self.text_trader_path}, labelled as data from outside trading-agent; read it with read_file. The original is {self.trader_path}.]'

    def to_json_dictionary(self) -> dict[str, Any]:
        """Converts the attachment to a dictionary that json.dumps can write.

        Returns:
            dict[str, Any]: Every field, with the kind as its name.
        """
        dictionary = dataclasses.asdict(self)
        dictionary['kind'] = str(self.kind)
        return dictionary

    @classmethod
    def from_json_dictionary(cls, dictionary: dict[str, Any]) -> Self:
        """Reads an attachment written by to_json_dictionary.

        Args:
            dictionary (dict[str, Any]): The fields.

        Returns:
            Attachment: The attachment.

        Raises:
            KeyError: A field is missing.
            ValueError: The kind is not one this version knows.
        """
        fields = dict(dictionary)
        fields['kind'] = AttachmentKind(fields['kind'])
        return cls(**fields)

    def stored_file(self) -> Path:
        """The stored file.

        Returns:
            Path: The absolute path of the uploaded file.
        """
        return Path(self.path)

    def _readable_size(self) -> str:
        """The file's size in words a person reads easily.

        Returns:
            str: Such as "240 KB" or "3.1 MB".
        """
        if self.size_bytes < 1024 * 1024:
            kilobytes = max(1, round(self.size_bytes / 1024))
            return f'{kilobytes} KB'
        return f'{self.size_bytes / (1024 * 1024):.1f} MB'
