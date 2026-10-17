# excel_text_reader.py

Uses openpyxl 3.1.5.

- `read_only=True` streams the rows, so a large workbook does not have to fit in memory as cell objects.
- `data_only=True` reads the values Excel last calculated rather than the formulas, because the desk wants the numbers a person sees. A workbook written by a program that never calculated it would show empty cells there; files saved by Excel or Google Sheets carry the values.
- Cells are separated by tabs, one row per line, each sheet under `--- Sheet name ---`. Tabs were chosen over commas because cell text often contains commas.

`workbook.close()` is needed with `read_only=True`, which keeps the file open while rows are read.

Only `.xlsx` is accepted; the old `.xls` format needs a different parser.
