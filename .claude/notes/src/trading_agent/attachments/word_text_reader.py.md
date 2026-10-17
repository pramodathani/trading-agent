# word_text_reader.py

Uses python-docx 1.2.0. It reads paragraphs first, then every table, each row with its cells joined by ` | `, because python-docx keeps paragraphs and tables in separate lists and a table read as loose paragraphs loses which value belongs to which column.

Only `.docx` is accepted. The old binary `.doc` format needs a different parser (or LibreOffice), and Word has saved `.docx` by default since 2007.

python-docx raises `PackageNotFoundError` for a file that is not a Word package, `BadZipFile` for one that is not a zip at all, and `KeyError` or `ValueError` for a damaged package; all become `TextReadError`.
