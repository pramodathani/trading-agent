"""Keeps the files the user sends with messages, in each desk's uploads folder.

Each upload gets its own folder, named by its identifier, under the India date it arrived:

  desks/<desk>/uploads/2026-10-17/3f9a1c2b7d4e/
    report.pdf        the file as it was sent
    text.txt          for a document, its text, labelled as data from outside trading-agent
    attachment.json   what the store knows about it

A picture is checked to be a real PNG, JPEG, WebP or GIF by its contents. A document is turned into text once, when it arrives, so every model reads the same text and nothing has to be parsed again. The text file starts and ends with the same marker lines that label web pages, because a document can come from anywhere and must not be able to give the desk instructions. Uploads are kept: the desk can come back to a document weeks later.

Typical usage example:

  store = AttachmentStore(layout)
  attachment = store.save('main', 'report.pdf', data)
  same = store.find('main', attachment.attachment_id)
"""

import datetime
import json
import re
import shutil
import uuid
import zoneinfo
from collections.abc import Callable, Sequence
from pathlib import Path

from trading_agent.attachments import attachment as attachment_module
from trading_agent.attachments import excel_text_reader
from trading_agent.attachments import image_preparer as image_preparer_module
from trading_agent.attachments import pdf_text_reader
from trading_agent.attachments import plain_text_reader
from trading_agent.attachments import text_reader
from trading_agent.attachments import word_text_reader
from trading_agent.extensions import untrusted_text as untrusted_text_module
from trading_agent.workspace import workspace_layout

MAXIMUM_BYTES = 20 * 1024 * 1024
IMAGE_EXTENSIONS = (
    '.png',
    '.jpg',
    '.jpeg',
    '.webp',
    '.gif',
)
_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')
_MAXIMUM_TEXT_CHARACTERS = 2_000_000
_IDENTIFIER_PATTERN = re.compile(r'^[0-9a-f]{12}$')
_UNSAFE_CHARACTERS = re.compile(r'[^A-Za-z0-9._ -]')
_LONGEST_NAME = 120
_TEXT_FILE_NAME = 'text.txt'
_RECORD_FILE_NAME = 'attachment.json'
_NO_TEXT_PROBLEM = 'it contains no text. A scanned PDF holds pictures of its pages, so ask the user to send the pages as pictures.'


class AttachmentRefusedError(ValueError):
    """An upload cannot be accepted: it is empty, too large, of a type not taken, or damaged."""


class AttachmentNotFoundError(LookupError):
    """No upload has that identifier on that desk."""


class AttachmentStore:
    """Every desk's uploads."""

    def __init__(
        self,
        layout: workspace_layout.WorkspaceLayout,
        image_preparer: image_preparer_module.ImagePreparer | None = None,
        readers: Sequence[text_reader.TextReader] | None = None,
        untrusted_text: untrusted_text_module.UntrustedText | None = None,
        clock: Callable[[], datetime.datetime] | None = None,
    ):
        """Creates the store.

        Args:
            layout (workspace_layout.WorkspaceLayout): Where the desk folders are.
            image_preparer (image_preparer_module.ImagePreparer | None): Checks pictures; None for a new one.
            readers (Sequence[text_reader.TextReader] | None): The document readers; None for PDF, Word, Excel and plain text.
            untrusted_text (untrusted_text_module.UntrustedText | None): Labels document text as data; None for a new one.
            clock (Callable[[], datetime.datetime] | None): Returns the current time; None uses the system clock. Tests replace it.
        """
        self._layout = layout
        self._image_preparer = (
            image_preparer or image_preparer_module.ImagePreparer()
        )
        if readers is None:
            readers = [
                pdf_text_reader.PdfTextReader(),
                word_text_reader.WordTextReader(),
                excel_text_reader.ExcelTextReader(),
                plain_text_reader.PlainTextReader(),
            ]
        self._readers = list(readers)
        self._untrusted_text = (
            untrusted_text or untrusted_text_module.UntrustedText()
        )
        self._clock = clock or self._real_now

    def accepted_extensions(self) -> list[str]:
        """Every file ending the store takes.

        Returns:
            list[str]: The picture endings, then the document endings.
        """
        extensions = list(IMAGE_EXTENSIONS)
        for reader in self._readers:
            extensions.extend(reader.extensions)
        return extensions

    def save(
        self,
        desk_name: str,
        file_name: str,
        data: bytes,
    ) -> attachment_module.Attachment:
        """Stores one upload, and reads a document's text.

        Args:
            desk_name (str): The desk it is for.
            file_name (str): The file's name as the user sent it.
            data (bytes): The file's contents.

        Returns:
            attachment_module.Attachment: The stored upload.

        Raises:
            AttachmentRefusedError: The file is empty, larger than 20 MB, of a type not taken, or a damaged picture.
        """
        self._check_size(file_name, data)
        safe_name = self._safe_name(file_name)
        reader = self._reader_for(safe_name)
        is_image = Path(safe_name).suffix.lower() in IMAGE_EXTENSIONS
        if not is_image and reader is None:
            raise AttachmentRefusedError(
                f'{file_name} is not a type the desks can use. Send a picture or one of: {", ".join(self.accepted_extensions())}.'
            )
        now = self._clock()
        attachment_id = uuid.uuid4().hex[:12]
        folder = (
            self._layout.uploads_directory(desk_name)
            / f'{now.astimezone(_INDIA):%Y-%m-%d}'
            / attachment_id
        )
        folder.mkdir(parents=True)
        stored = folder / safe_name
        stored.write_bytes(data)
        if is_image:
            attachment = self._image_attachment(
                desk_name, file_name, attachment_id, stored, len(data), now
            )
        else:
            attachment = self._document_attachment(
                desk_name,
                file_name,
                attachment_id,
                stored,
                reader,
                now,
            )
        (folder / _RECORD_FILE_NAME).write_text(
            json.dumps(attachment.to_json_dictionary(), indent=2),
            encoding='utf-8',
        )
        return attachment

    def find(
        self,
        desk_name: str,
        attachment_id: str,
    ) -> attachment_module.Attachment:
        """Finds one of a desk's uploads.

        Args:
            desk_name (str): The desk.
            attachment_id (str): The upload's identifier.

        Returns:
            attachment_module.Attachment: The upload.

        Raises:
            AttachmentNotFoundError: The desk has no upload with that identifier.
        """
        if not _IDENTIFIER_PATTERN.match(attachment_id):
            raise AttachmentNotFoundError(
                f'{attachment_id!r} is not an upload identifier'
            )
        uploads = self._layout.uploads_directory(desk_name)
        desk_directory = self._layout.desk_directory(desk_name)
        for record in uploads.glob(f'*/{attachment_id}/{_RECORD_FILE_NAME}'):
            dictionary = json.loads(record.read_text(encoding='utf-8'))
            dictionary['path'] = str(desk_directory / dictionary['desk_path'])
            return attachment_module.Attachment.from_json_dictionary(dictionary)
        raise AttachmentNotFoundError(
            f'The {desk_name} desk has no upload {attachment_id}'
        )

    def _image_attachment(
        self,
        desk_name: str,
        file_name: str,
        attachment_id: str,
        stored: Path,
        size_bytes: int,
        now: datetime.datetime,
    ) -> attachment_module.Attachment:
        """Checks a stored picture and describes it.

        Args:
            desk_name (str): The desk.
            file_name (str): The name the user sent.
            attachment_id (str): The upload's identifier.
            stored (Path): The stored file.
            size_bytes (int): Its size.
            now (datetime.datetime): When it arrived.

        Returns:
            attachment_module.Attachment: The picture.

        Raises:
            AttachmentRefusedError: The file is not a picture that can be read; its folder is removed.
        """
        try:
            media_type = self._image_preparer.check(stored)
        except image_preparer_module.ImageError as error:
            shutil.rmtree(stored.parent)
            raise AttachmentRefusedError(f'{file_name}: {error}.') from error
        return attachment_module.Attachment(
            attachment_id=attachment_id,
            desk=desk_name,
            kind=attachment_module.AttachmentKind.IMAGE,
            file_name=file_name,
            media_type=media_type,
            size_bytes=size_bytes,
            path=str(stored),
            desk_path=self._desk_path(desk_name, stored),
            text_desk_path=None,
            text_characters=None,
            page_count=None,
            problem='',
            created_at=now.astimezone(datetime.UTC).isoformat(),
        )

    def _document_attachment(
        self,
        desk_name: str,
        file_name: str,
        attachment_id: str,
        stored: Path,
        reader: text_reader.TextReader,
        now: datetime.datetime,
    ) -> attachment_module.Attachment:
        """Reads a stored document's text into text.txt and describes it.

        A document whose text cannot be read is still kept, with the reason, so the desk can tell the user what went wrong.

        Args:
            desk_name (str): The desk.
            file_name (str): The name the user sent.
            attachment_id (str): The upload's identifier.
            stored (Path): The stored file.
            reader (text_reader.TextReader): The reader for its format.
            now (datetime.datetime): When it arrived.

        Returns:
            attachment_module.Attachment: The document.
        """
        text_desk_path = None
        text_characters = None
        page_count = None
        problem = ''
        try:
            extracted = reader.read(stored)
        except text_reader.TextReadError as error:
            problem = f'{error}.'
        else:
            page_count = extracted.page_count
            text = self._shortened(extracted.text)
            if self._has_words(text):
                text_file = stored.parent / _TEXT_FILE_NAME
                text_file.write_text(
                    self._untrusted_text.wrap(
                        f'the uploaded file {file_name}', text
                    ),
                    encoding='utf-8',
                )
                text_desk_path = self._desk_path(desk_name, text_file)
                text_characters = len(text)
            else:
                problem = _NO_TEXT_PROBLEM
        return attachment_module.Attachment(
            attachment_id=attachment_id,
            desk=desk_name,
            kind=attachment_module.AttachmentKind.DOCUMENT,
            file_name=file_name,
            media_type=reader.media_type,
            size_bytes=stored.stat().st_size,
            path=str(stored),
            desk_path=self._desk_path(desk_name, stored),
            text_desk_path=text_desk_path,
            text_characters=text_characters,
            page_count=page_count,
            problem=problem,
            created_at=now.astimezone(datetime.UTC).isoformat(),
        )

    def _check_size(self, file_name: str, data: bytes) -> None:
        """Refuses an empty file or one larger than 20 MB.

        Args:
            file_name (str): The file's name, for the message.
            data (bytes): Its contents.

        Raises:
            AttachmentRefusedError: The file is empty or too large.
        """
        if not data:
            raise AttachmentRefusedError(f'{file_name} is empty.')
        if len(data) > MAXIMUM_BYTES:
            megabytes = len(data) / (1024 * 1024)
            raise AttachmentRefusedError(
                f'{file_name} is {megabytes:.1f} MB; the most a desk takes is 20 MB.'
            )

    def _reader_for(self, file_name: str) -> text_reader.TextReader | None:
        """Finds the reader for a document.

        Args:
            file_name (str): The file's name.

        Returns:
            text_reader.TextReader | None: The reader whose endings match, or None.
        """
        for reader in self._readers:
            if reader.takes(file_name):
                return reader
        return None

    def _safe_name(self, file_name: str) -> str:
        """Turns the sent name into one that is safe to store: no folders, no odd characters, not too long.

        Args:
            file_name (str): The name as sent.

        Returns:
            str: The name to store the file under, keeping its ending.
        """
        base_name = file_name.replace('\\', '/').split('/')[-1]
        cleaned = _UNSAFE_CHARACTERS.sub('_', base_name).strip(' .')
        suffix = Path(cleaned).suffix.lower()
        stem = Path(cleaned).stem.strip(' .') or 'file'
        return f'{stem[: _LONGEST_NAME - len(suffix)]}{suffix}'

    def _shortened(self, text: str) -> str:
        """Cuts very long document text, saying so at the end.

        Args:
            text (str): The text.

        Returns:
            str: The text, at most two million characters plus the note.
        """
        if len(text) <= _MAXIMUM_TEXT_CHARACTERS:
            return text
        return f'{text[:_MAXIMUM_TEXT_CHARACTERS]}\n[The rest of the document, {len(text) - _MAXIMUM_TEXT_CHARACTERS:,} more characters, was left out.]'

    def _has_words(self, text: str) -> bool:
        """Says whether text holds anything besides page headings and spaces.

        Args:
            text (str): The extracted text.

        Returns:
            bool: True when some line is neither empty nor a page heading.
        """
        for line in text.splitlines():
            stripped = line.strip()
            if stripped and not re.fullmatch(r'--- Page \d+ ---', stripped):
                return True
        return False

    def _desk_path(self, desk_name: str, path: Path) -> str:
        """A stored file's path relative to the desk folder, as the desk's tools take it.

        Args:
            desk_name (str): The desk.
            path (Path): The file.

        Returns:
            str: The relative path with forward slashes.
        """
        return path.relative_to(
            self._layout.desk_directory(desk_name)
        ).as_posix()

    def _real_now(self) -> datetime.datetime:
        """The current time.

        Returns:
            datetime.datetime: Now, in UTC.
        """
        return datetime.datetime.now(datetime.UTC)
