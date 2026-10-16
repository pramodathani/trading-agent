"""A logging filter that hides access tokens in uvicorn's log lines.

uvicorn logs the full address of every request, and a WebSocket carries its access token in the address as `?token=...`. This filter replaces the token's value before the line is written.

Typical usage example:

  TokenRedactingFilter().install()
"""

import logging
import re

_TOKEN_PATTERN = re.compile(r'(token=)[^&\s"]+')
_REPLACEMENT = r'\1***'
_UVICORN_LOGGER_NAMES = [
    'uvicorn.access',
    'uvicorn.error',
]


class TokenRedactingFilter(logging.Filter):
    """Rewrites a log record so that no `token=` value survives."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Replaces token values in the record's message and arguments.

        Args:
            record (logging.LogRecord): The record about to be written.

        Returns:
            bool: Always True, so that the record is still written.
        """
        record.msg = _TOKEN_PATTERN.sub(_REPLACEMENT, str(record.msg))
        if isinstance(record.args, tuple):
            redacted_arguments = []
            for argument in record.args:
                if isinstance(argument, str):
                    argument = _TOKEN_PATTERN.sub(_REPLACEMENT, argument)
                redacted_arguments.append(argument)
            record.args = tuple(redacted_arguments)
        return True

    def install(self) -> None:
        """Adds this filter to uvicorn's access and error loggers.

        Call it after uvicorn has configured its logging, because configuring replaces the loggers' handlers.
        """
        for logger_name in _UVICORN_LOGGER_NAMES:
            logging.getLogger(logger_name).addFilter(self)
