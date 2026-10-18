"""Formats money, numbers, durations and times the way the web page does.

Money uses Indian digit grouping and the rupee sign, and times are India clock times.

Typical usage example:

  formatter = Formatter()
  formatter.money(123456.7)  # '₹1,23,456.70'
  formatter.elapsed_text(137)  # '2m 17s'
"""

import datetime
import zoneinfo

_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')
_MISSING = '—'
_MINUS = '−'


class Formatter:
    """Turns numbers and moments into short text for the terminal."""

    def grouped(self, value: float, decimals: int = 2) -> str:
        """Writes a number with Indian digit grouping.

        Args:
            value (float): The number.
            decimals (int): How many digits to keep after the point.

        Returns:
            str: Such as "1,23,456.70" for 123456.7, with a leading "-" when negative.
        """
        sign = ''
        if value < 0:
            sign = '-'
            value = -value
        fixed = f'{value:.{decimals}f}'
        whole = fixed
        fraction = ''
        if decimals > 0:
            whole, fraction = fixed.split('.')
            fraction = '.' + fraction
        if len(whole) > 3:
            head = whole[:-3]
            tail = whole[-3:]
            groups = []
            while len(head) > 2:
                groups.insert(0, head[-2:])
                head = head[:-2]
            if head:
                groups.insert(0, head)
            whole = ','.join(groups) + ',' + tail
        return f'{sign}{whole}{fraction}'

    def money(self, amount: float | None) -> str:
        """Formats an amount of money.

        Args:
            amount (float | None): The amount in rupees, or None.

        Returns:
            str: Such as "₹1,23,456.70", or "—" when missing.
        """
        if amount is None:
            return _MISSING
        if amount < 0:
            return f'-₹{self.grouped(-amount)}'
        return f'₹{self.grouped(amount)}'

    def signed_money(self, amount: float | None) -> str:
        """Formats a profit or loss with its sign.

        Args:
            amount (float | None): The amount in rupees, or None.

        Returns:
            str: Such as "+₹1,250.00" or "−₹300.00", or "—" when missing.
        """
        if amount is None:
            return _MISSING
        if amount > 0:
            return f'+₹{self.grouped(amount)}'
        if amount < 0:
            return f'{_MINUS}₹{self.grouped(-amount)}'
        return f'₹{self.grouped(0)}'

    def price_text(self, value: float | None) -> str:
        """Formats a price.

        Args:
            value (float | None): The price, or None.

        Returns:
            str: Such as "2,945.50", or "—" when missing.
        """
        if value is None:
            return _MISSING
        return self.grouped(value)

    def number(self, value: object) -> str:
        """Formats a whole number from an event payload.

        Args:
            value (object): The value, which may be missing or not a number.

        Returns:
            str: Such as "12,345", or "?" when the value is not a number.
        """
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return '?'
        if isinstance(value, float) and not value.is_integer():
            return self.grouped(value, 1)
        return self.grouped(value, 0)

    def moment(self, iso_text: str) -> datetime.datetime | None:
        """Reads an ISO timestamp from the gateway.

        Args:
            iso_text (str): Such as "2026-10-19T04:30:00+00:00".

        Returns:
            datetime.datetime | None: The moment in India time, or None when the text is not a timestamp.
        """
        try:
            moment = datetime.datetime.fromisoformat(iso_text)
        except ValueError:
            return None
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=datetime.UTC)
        return moment.astimezone(_INDIA)

    def time(self, iso_text: str) -> str:
        """Formats a moment as an India clock time.

        Args:
            iso_text (str): An ISO timestamp.

        Returns:
            str: Such as "10:04:31", or the text itself when it is not a timestamp.
        """
        moment = self.moment(iso_text)
        if moment is None:
            return iso_text
        return moment.strftime('%H:%M:%S')

    def day_time(self, iso_text: str) -> str:
        """Formats a moment as a day and an India clock time.

        Args:
            iso_text (str): An ISO timestamp.

        Returns:
            str: Such as "19 Oct, 10:04", or the text itself when it is not a timestamp.
        """
        moment = self.moment(iso_text)
        if moment is None:
            return iso_text
        return f'{moment.day} {moment.strftime("%b, %H:%M")}'

    def file_size(self, size_bytes: int) -> str:
        """Formats a file size.

        Args:
            size_bytes (int): The size in bytes.

        Returns:
            str: Such as "340 KB" or "2.4 MB".
        """
        if size_bytes < 1024 * 1024:
            return f'{max(1, round(size_bytes / 1024))} KB'
        return f'{size_bytes / (1024 * 1024):.1f} MB'

    def token_count(self, tokens: float) -> str:
        """Formats a token count.

        Args:
            tokens (float): The count.

        Returns:
            str: Such as "850", "12.3k" or "1M".
        """
        if tokens < 1000:
            return str(round(tokens))
        if tokens < 1000000:
            return f'{self._one_decimal(tokens / 1000)}k'
        return f'{self._one_decimal(tokens / 1000000)}M'

    def share(self, part: float, whole: float) -> str:
        """Formats a part of a whole as a percentage.

        Args:
            part (float): The part.
            whole (float): The whole.

        Returns:
            str: Such as "34.2%", or "—" when the whole is not positive.
        """
        if whole <= 0:
            return _MISSING
        return f'{100 * part / whole:.1f}%'

    def elapsed_text(self, seconds: int) -> str:
        """Formats a duration the way Claude Code shows it.

        Args:
            seconds (int): The duration in seconds.

        Returns:
            str: Such as "12s" or "2m 17s".
        """
        if seconds < 60:
            return f'{seconds}s'
        return f'{seconds // 60}m {seconds % 60}s'

    def _one_decimal(self, value: float) -> str:
        """Writes a number with at most one decimal, dropping a trailing ".0".

        Args:
            value (float): The number.

        Returns:
            str: Such as "12.3" or "12".
        """
        text = f'{value:.1f}'
        if text.endswith('.0'):
            return text[:-2]
        return text
