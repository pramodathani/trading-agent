"""Checks that a DeepSeek backend has its API key and that DeepSeek accepts it.

The key is never shown. The check lists DeepSeek's models, a request that costs nothing.

Typical usage example:

  result = DeepSeekBackendCheck('deepseek', backend_configuration, secrets).run()
"""

import httpx

from trading_agent.configuration import agent_configuration
from trading_agent.configuration import secrets as secrets_module
from trading_agent.doctor import doctor_check

_TIMEOUT_SECONDS = 5.0
_UNAUTHORIZED = 401


class DeepSeekBackendCheck(doctor_check.DoctorCheck):
    """Checks one backend of kind "deepseek"."""

    def __init__(
        self,
        backend_name: str,
        backend_configuration: agent_configuration.BackendConfiguration,
        secrets: secrets_module.Secrets,
    ):
        """Creates the check.

        Args:
            backend_name (str): The backend's name in trading_agent.toml.
            backend_configuration (agent_configuration.BackendConfiguration): Its settings.
            secrets (secrets_module.Secrets): The secrets, holding the key.
        """
        self.name = f'Backend {backend_name} (DeepSeek)'
        self._backend_configuration = backend_configuration
        self._secrets = secrets

    def run(self) -> doctor_check.CheckResult:
        """Checks the key is set, then that DeepSeek answers with it.

        Returns:
            doctor_check.CheckResult: OK when DeepSeek accepts the key, failed when the key is missing or refused or DeepSeek cannot be reached.
        """
        variable = self._backend_configuration.api_key_variable or 'TRADING_AGENT_OPENAI_API_KEY'
        if self._backend_configuration.api_key_variable is None:
            key = self._secrets.openai_api_key
        else:
            key = self._secrets.named(variable)
        if not key:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.FAILED,
                f'{variable} is not set in .env.',
            )
        base_url = self._backend_configuration.base_url
        try:
            response = httpx.get(
                f'{base_url}/models',
                headers={
                    'Authorization': f'Bearer {key}',
                },
                timeout=_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as error:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.FAILED,
                f'DeepSeek at {base_url} did not answer: {error!r}',
            )
        if response.status_code == _UNAUTHORIZED:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.FAILED,
                f'DeepSeek refused the key in {variable}.',
            )
        if response.is_error:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.FAILED,
                f'DeepSeek answered HTTP {response.status_code}.',
            )
        model = self._backend_configuration.model
        listed = []
        for entry in response.json().get('data', []):
            listed.append(str(entry.get('id', '')))
        if model not in listed:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.WARNING,
                f'The key works, but {model!r} is not among the models DeepSeek lists: {", ".join(listed)}.',
            )
        return doctor_check.CheckResult(
            doctor_check.CheckStatus.OK,
            f'The key in {variable} works and {model} is available.',
        )
