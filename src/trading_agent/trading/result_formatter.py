"""Turns what tradingmachine returns into compact text for a model.

Tables of candles become CSV, which models read well and which costs few tokens; only the last rows are kept, with a note of how many there were. Dictionaries and lists become JSON. Dates and NumPy values are written as plain text and numbers, and not-a-number values as null.

Typical usage example:

  text = ResultFormatter().format(frame, rows=50)
"""

import datetime
import json
import math
from typing import Any

import numpy
import pandas

_MAXIMUM_CHARACTERS = 15000


class ResultFormatter:
    """Formats tradingmachine values as text."""

    def format(self, value: Any, rows: int = 50) -> str:
        """Formats any value tradingmachine returns.

        Args:
            value (Any): A DataFrame, a dictionary, a list or a plain value; None means no data.
            rows (int): For a table, how many of the last rows to keep.

        Returns:
            str: The text, at most 15,000 characters.
        """
        if value is None:
            return 'No data.'
        if isinstance(value, pandas.DataFrame):
            text = self._table(value, rows)
        else:
            text = json.dumps(self._plain(value), indent=1, ensure_ascii=False)
        if len(text) > _MAXIMUM_CHARACTERS:
            text = (
                text[:_MAXIMUM_CHARACTERS]
                + '\n[cut: the answer was too long; ask for fewer rows]'
            )
        return text

    def _table(self, frame: pandas.DataFrame, rows: int) -> str:
        """Writes the last rows of a table as CSV.

        Args:
            frame (pandas.DataFrame): The table.
            rows (int): How many of the last rows to keep.

        Returns:
            str: A line saying how many rows there are, then the CSV.
        """
        shown = frame.tail(rows)
        header = (
            f'{len(frame)} rows; the last {len(shown)} are shown, oldest first.'
        )
        return header + '\n' + shown.to_csv(index=False).strip()

    def _plain(self, value: Any) -> Any:
        """Converts a value into types json.dumps can write.

        Args:
            value (Any): The value.

        Returns:
            Any: The same value made of dictionaries, lists, strings, numbers, booleans and None.
        """
        if isinstance(value, dict):
            plain = {}
            for key, item in value.items():
                plain[str(key)] = self._plain(item)
            return plain
        if isinstance(value, (list, tuple)):
            return [self._plain(item) for item in value]
        if isinstance(value, pandas.DataFrame):
            return self._plain(value.to_dict(orient='records'))
        if isinstance(
            value, (datetime.date, datetime.datetime, pandas.Timestamp)
        ):
            return value.isoformat()
        if isinstance(value, numpy.generic):
            value = value.item()
        if isinstance(value, float) and math.isnan(value):
            return None
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)
