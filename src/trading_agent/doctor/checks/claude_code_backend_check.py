"""Checks that Claude Code is installed and can use the Max subscription.

The subscription is used through a token from `claude setup-token`. An ANTHROPIC_API_KEY in the environment would make Claude Code bill the API instead, so its presence is a failure.

Typical usage example:

  result = ClaudeCodeBackendCheck('claude', secrets).run()
"""

import os
import shutil
import subprocess
from pathlib import Path

import claude_agent_sdk

from trading_agent.configuration import secrets as secrets_module
from trading_agent.doctor import doctor_check

_TIMEOUT_SECONDS = 10.0


class ClaudeCodeBackendCheck(doctor_check.DoctorCheck):
    """Checks one backend of kind "claude_code"."""

    def __init__(self, backend_name: str, secrets: secrets_module.Secrets):
        """Creates the check.

        Args:
            backend_name (str): The backend's name in trading_agent.toml.
            secrets (secrets_module.Secrets): The secrets read from the environment and .env.
        """
        self.name = f'Backend {backend_name} (Claude Code)'
        self._secrets = secrets

    def run(self) -> doctor_check.CheckResult:
        """Checks the CLI, the absence of an API key, and the subscription token.

        Returns:
            doctor_check.CheckResult: OK when everything is ready, a warning when only the token is missing, failed otherwise.
        """
        if 'ANTHROPIC_API_KEY' in os.environ:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.FAILED,
                'ANTHROPIC_API_KEY is set, so Claude Code would bill the API instead of your Max subscription; unset it.',
            )
        claude_path = self._claude_path()
        if claude_path is None:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.FAILED,
                'Neither the Agent SDK bundled claude nor a claude command on PATH was found.',
            )
        completed = subprocess.run(
            [
                claude_path,
                '--version',
            ],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            check=False,
        )
        version = completed.stdout.strip()
        if not self._secrets.claude_code_oauth_token:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.WARNING,
                f'{version} at {claude_path}, but TRADING_AGENT_CLAUDE_CODE_OAUTH_TOKEN is not set (create it with claude setup-token).',
            )
        return doctor_check.CheckResult(
            doctor_check.CheckStatus.OK,
            f'{version} at {claude_path}; the subscription token is set.',
        )

    def _claude_path(self) -> str | None:
        """Finds the Claude Code program the Agent SDK will actually run.

        The SDK prefers the copy bundled inside the package over the one on PATH, so the bundled copy is checked first.

        Returns:
            str | None: The program's path, or None when neither exists.
        """
        bundled_path = (
            Path(claude_agent_sdk.__file__).parent / '_bundled' / 'claude'
        )
        if bundled_path.is_file():
            return str(bundled_path)
        return shutil.which('claude')
