"""Reads files that already are text: plain text, Markdown, CSV, TSV and JSON.

Typical usage example:

  extracted = PlainTextReader().read(Path('trades.csv'))
"""

from pathlib import Path

from trading_agent.attachments import text_reader


class PlainTextReader(text_reader.TextReader):
    """Reads a text file as it is."""

    extensions = (
        '.txt',
        '.md',
        '.csv',
        '.tsv',
        '.json',
    )
    media_type = 'text/plain'

    def read(self, path: Path) -> text_reader.ExtractedText:
        """Reads the file, replacing bytes that are not UTF-8.

        Args:
            path (Path): The file.

        Returns:
            text_reader.ExtractedText: Its text.

        Raises:
            TextReadError: The file cannot be opened.
        """
        try:
            text = path.read_text(encoding='utf-8-sig', errors='replace')
        except OSError as error:
            raise text_reader.TextReadError(
                f'the file cannot be opened ({error})'
            ) from error
        return text_reader.ExtractedText(text=text)
