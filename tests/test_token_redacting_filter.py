"""Tests for hiding access tokens in log lines."""

import logging

from trading_agent.gateway import token_redacting_filter


def _record(message: str, arguments: tuple) -> logging.LogRecord:
    """Builds a log record the way uvicorn does, with %-style arguments.

    Args:
        message (str): The format string.
        arguments (tuple): The values for the format string.

    Returns:
        logging.LogRecord: The record.
    """
    return logging.LogRecord(
        name='uvicorn.error',
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=arguments,
        exc_info=None,
    )


class TestTokenRedactingFilter:
    """Tests for TokenRedactingFilter."""

    def test_token_in_arguments_is_hidden(self) -> None:
        """A token passed as a log argument is replaced with stars."""
        record = _record(
            '%s - "WebSocket %s" [accepted]',
            (
                '127.0.0.1:5000',
                '/ws/events?token=secret-value-123',
            ),
        )

        token_redacting_filter.TokenRedactingFilter().filter(record)

        assert 'secret-value-123' not in record.getMessage()
        assert 'token=***' in record.getMessage()

    def test_token_in_message_is_hidden_and_other_parameters_kept(self) -> None:
        """A token in the message itself is hidden, and parameters after it survive."""
        record = _record('GET /x?token=abc&desk=main', ())

        token_redacting_filter.TokenRedactingFilter().filter(record)

        assert record.getMessage() == 'GET /x?token=***&desk=main'


def test_bot_token_in_a_telegram_address_is_masked() -> None:
    """A bot token inside a Telegram address, as httpx logs it, is replaced."""
    record = logging.LogRecord(
        'httpx',
        logging.INFO,
        __file__,
        1,
        'HTTP Request: %s %s',
        (
            'POST',
            _Address(
                'https://api.telegram.org/bot123456789:AAH-secret_PART/getUpdates'
            ),
        ),
        None,
    )

    token_redacting_filter.TokenRedactingFilter().filter(record)

    assert 'AAH-secret_PART' not in record.getMessage()
    assert '/bot***/getUpdates' in record.getMessage()


class _Address:
    """An object that is not a string but prints as an address, like httpx.URL."""

    def __init__(self, text: str):
        """Creates the address.

        Args:
            text (str): The address.
        """
        self._text = text

    def __str__(self) -> str:
        """The address as text.

        Returns:
            str: The address.
        """
        return self._text
