"""Reads an Excel workbook (.xlsx) with openpyxl: every sheet, one row per line, cells separated by tabs.

Formulas are read as the values Excel last calculated, which is what a person sees. The older .xls format is a different, binary format that openpyxl cannot open, so it is not accepted.

Typical usage example:

  extracted = ExcelTextReader().read(Path('positions.xlsx'))
"""

import zipfile
from pathlib import Path

import openpyxl
import openpyxl.utils.exceptions

from trading_agent.attachments import text_reader


class ExcelTextReader(text_reader.TextReader):
    """Reads a .xlsx file."""

    extensions = ('.xlsx',)
    media_type = (
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

    def read(self, path: Path) -> text_reader.ExtractedText:
        """Reads every sheet under a heading with its name.

        Args:
            path (Path): The workbook.

        Returns:
            text_reader.ExtractedText: Its text.

        Raises:
            TextReadError: The file is damaged or is not a .xlsx file.
        """
        try:
            workbook = openpyxl.load_workbook(
                path, read_only=True, data_only=True
            )
        except (
            openpyxl.utils.exceptions.InvalidFileException,
            zipfile.BadZipFile,
            KeyError,
            OSError,
        ) as error:
            raise text_reader.TextReadError(
                f'the workbook cannot be read ({type(error).__name__}: {error})'
            ) from error
        lines = []
        try:
            for sheet in workbook.worksheets:
                lines.append(f'--- Sheet {sheet.title} ---')
                for row in sheet.iter_rows(values_only=True):
                    cells = []
                    for value in row:
                        cells.append('' if value is None else str(value))
                    lines.append('\t'.join(cells).rstrip())
                lines.append('')
        finally:
            workbook.close()
        return text_reader.ExtractedText(text='\n'.join(lines).strip())
