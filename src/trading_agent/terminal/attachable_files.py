"""Decides which local files can be attached to a message, and finds them in typed or pasted text.

The rules copy the web page's: pictures (PNG, JPEG, WebP, GIF) and documents (PDF, Word, Excel, CSV, TSV, text, Markdown, JSON), up to 20 MB each. A file dragged onto a terminal window arrives as its pasted path, sometimes quoted, with escaped spaces, or as a file:// address, so pasted text is read in all those forms.

Typical usage example:

  files = AttachableFiles()
  files.from_paste("'/home/me/chart one.png'")  # [Path('/home/me/chart one.png')]
  files.problem(Path('notes.exe'))  # 'notes.exe is not a picture or document the desk can read'
"""

import shlex
import urllib.parse
from pathlib import Path

_ACCEPTED_SUFFIXES = (
    '.png',
    '.jpg',
    '.jpeg',
    '.webp',
    '.gif',
    '.pdf',
    '.docx',
    '.xlsx',
    '.csv',
    '.tsv',
    '.txt',
    '.md',
    '.json',
)
_MOST_BYTES = 20 * 1024 * 1024
_MOST_SUGGESTIONS = 30


class AttachableFiles:
    """The rules for files that can go with a message."""

    def problem(self, path: Path) -> str | None:
        """Says why a file cannot be attached.

        Args:
            path (Path): The file.

        Returns:
            str | None: The reason, or None when it can be attached.
        """
        if not path.is_file():
            return f'{path} is not a file'
        if path.suffix.lower() not in _ACCEPTED_SUFFIXES:
            return f'{path.name} is not a picture or document the desk can read'
        if path.stat().st_size > _MOST_BYTES:
            return f'{path.name} is larger than 20 MB'
        return None

    def from_paste(self, text: str) -> list[Path]:
        """Reads pasted text as dropped files.

        Args:
            text (str): The pasted text.

        Returns:
            list[Path]: The files, when every word of the text is an existing file; otherwise an empty list, so the text is pasted as text.
        """
        stripped = text.strip()
        if not stripped:
            return []
        try:
            words = shlex.split(stripped)
        except ValueError:
            return []
        paths = []
        for word in words:
            if word.startswith('file://'):
                word = urllib.parse.unquote(urllib.parse.urlparse(word).path)
            path = Path(word).expanduser()
            if not path.is_file():
                return []
            paths.append(path)
        return paths

    def mentioned(self, text: str) -> list[tuple[str, Path]]:
        """Finds @path words that name existing files.

        Args:
            text (str): The message.

        Returns:
            list[tuple[str, Path]]: Each @word as typed and the file it names.
        """
        found = []
        for word in text.split():
            if not word.startswith('@') or len(word) < 2:
                continue
            path = Path(word[1:]).expanduser()
            if path.is_file():
                found.append(
                    (
                        word,
                        path,
                    )
                )
        return found

    def suggestions(self, partial: str) -> list[str]:
        """Files and folders that start with a partly typed path, for the @ menu.

        Args:
            partial (str): The path typed after @, such as "docs/ch".

        Returns:
            list[str]: Matching paths as they would be typed, folders ending in "/", attachable files and folders only.
        """
        typed = Path(partial).expanduser()
        if partial.endswith('/') or not partial:
            folder = typed
            start = ''
        else:
            folder = typed.parent
            start = typed.name
        try:
            entries = sorted(folder.iterdir())
        except OSError:
            return []
        prefix = partial[: len(partial) - len(start)]
        found = []
        for entry in entries:
            if entry.name.startswith('.') and not start.startswith('.'):
                continue
            if not entry.name.lower().startswith(start.lower()):
                continue
            if entry.is_dir():
                found.append(f'{prefix}{entry.name}/')
            elif entry.suffix.lower() in _ACCEPTED_SUFFIXES:
                found.append(f'{prefix}{entry.name}')
            if len(found) >= _MOST_SUGGESTIONS:
                break
        return found
