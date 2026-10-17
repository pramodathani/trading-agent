"""A logging filter that hides tokens in the addresses that uvicorn and httpx log.

uvicorn logs the full address of every request, and a WebSocket carries its access token in the address as `?token=...`. httpx, which python-telegram-bot uses, logs every request too, and Telegram's addresses carry the bot token as `/bot<token>/`. This filter replaces both before the line is written.

Typical usage example:

  TokenRedactingFilter().install()
"""

import logging
import re

_TOKEN_PATTERN = re.compile(r'(token=)[^&\s"]+')
_REPLACEMENT = r'\1***'
_BOT_TOKEN_PATTERN = re.compile(r'(/bot)\d+:[A-Za-z0-9_-]+')
_BOT_REPLACEMENT = r'\1***'
_LOGGER_NAMES = [
    'uvicorn.access',
    'uvicorn.error',
    'httpx',
    'telegram',
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
        record.msg = self.redact(str(record.msg))
        if isinstance(record.args, tuple):
            redacted_arguments = []
            for argument in record.args:
                if not isinstance(argument, (int, float)):
                    argument = self.redact(str(argument))
                redacted_arguments.append(argument)
            record.args = tuple(redacted_arguments)
        return True

    def redact(self, text: str) -> str:
        """Masks every access token and bot token in a piece of text.

        Args:
            text (str): The text.

        Returns:
            str: The text with `token=` values and `/bot<token>` parts replaced by ***.
        """
        text = _TOKEN_PATTERN.sub(_REPLACEMENT, text)
        return _BOT_TOKEN_PATTERN.sub(_BOT_REPLACEMENT, text)

    def install(self) -> None:
        """Adds this filter to uvicorn's, httpx's and python-telegram-bot's loggers.

        It is also added to the root logger's handlers, because a logger's own filter does not see records from its child loggers, such as telegram.bot. Call it after uvicorn has configured its logging, because configuring replaces the loggers' handlers.
        """
        for logger_name in _LOGGER_NAMES:
            logging.getLogger(logger_name).addFilter(self)
        for handler in logging.getLogger().handlers:
            handler.addFilter(self)
