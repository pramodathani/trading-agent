"""Masks secrets in text before it is written down or shown.

It knows two kinds of secret: the exact values of the agent's own secrets and of tradingmachine's passwords and keys, read from their files, and the usual shapes of tokens (Anthropic tokens, bearer tokens, `token=` and `api-key` parameters), which catch secrets it was never told about.

Typical usage example:

  redactor = SecretRedactor.from_files(secrets, Path('/home/pramod/Projects/tradingmachine/.env'))
  safe = redactor.redact(payload)
"""

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Self

import dotenv

from trading_agent.configuration import secrets as secrets_module

REPLACEMENT = '[redacted]'
_MINIMUM_SECRET_LENGTH = 8
_SECRET_NAME_PATTERN = re.compile(r'PASSWORD|SECRET|TOKEN|KEY', re.IGNORECASE)
_SECRET_SHAPES = [
    re.compile(r'sk-ant-[A-Za-z0-9_\-]{10,}'),
    re.compile(r'(?i)(bearer\s+)[A-Za-z0-9._\-]{16,}'),
    re.compile(r'(?i)((?:access_)?token=)[^&\s"\']+'),
    re.compile(
        r'(?i)(api[-_]?(?:key|secret)["\']?\s*[:=]\s*["\']?)[^\s"\',&]+'
    ),
]


class SecretRedactor:
    """Replaces known secret values and token-shaped text with [redacted]."""

    def __init__(self, secret_values: Iterable[str]):
        """Creates the redactor.

        Args:
            secret_values (Iterable[str]): The exact secret values to mask; values shorter than 8 characters are ignored, because they would mask ordinary words.
        """
        values = set()
        for value in secret_values:
            if value and len(value) >= _MINIMUM_SECRET_LENGTH:
                values.add(value)
        self._secret_values = sorted(values, key=len, reverse=True)

    @classmethod
    def from_files(
        cls,
        secrets: secrets_module.Secrets,
        tradingmachine_environment_file: Path,
    ) -> Self:
        """Builds a redactor that knows the agent's secrets and tradingmachine's.

        Args:
            secrets (secrets_module.Secrets): The agent's own secrets.
            tradingmachine_environment_file (Path): tradingmachine's `.env`; its values whose names contain PASSWORD, SECRET, TOKEN or KEY are masked.

        Returns:
            SecretRedactor: The redactor.
        """
        values = [
            secrets.gateway_access_token,
            secrets.claude_code_oauth_token,
            secrets.openai_api_key,
            secrets.webhook_token,
            secrets.telegram_bot_token,
        ]
        if tradingmachine_environment_file.is_file():
            for name, value in dotenv.dotenv_values(
                tradingmachine_environment_file
            ).items():
                if value and _SECRET_NAME_PATTERN.search(name):
                    values.append(value)
        return cls(values)

    def redact(self, value: Any) -> Any:
        """Masks secrets in a value and everything inside it.

        Args:
            value (Any): A string, or a dictionary or list holding strings.

        Returns:
            Any: A copy with every secret replaced; other types are returned unchanged.
        """
        if isinstance(value, str):
            return self._redact_text(value)
        if isinstance(value, dict):
            redacted = {}
            for key, item in value.items():
                redacted[key] = self.redact(item)
            return redacted
        if isinstance(value, (list, tuple)):
            return [self.redact(item) for item in value]
        return value

    def _redact_text(self, text: str) -> str:
        """Masks secrets in one piece of text.

        Args:
            text (str): The text.

        Returns:
            str: The text with known values and token-shaped parts replaced.
        """
        for secret in self._secret_values:
            if secret in text:
                text = text.replace(secret, REPLACEMENT)
        for shape in _SECRET_SHAPES:
            if shape.groups:
                text = shape.sub(
                    lambda match: match.group(1) + REPLACEMENT, text
                )
            else:
                text = shape.sub(REPLACEMENT, text)
        return text
