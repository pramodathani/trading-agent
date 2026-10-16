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
