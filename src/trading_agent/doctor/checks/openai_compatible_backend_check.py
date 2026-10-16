"""Checks that an OpenAI-compatible backend's server answers.

A 401 answer means the server is running but wants an API key, which is reported as a warning until the key is configured.

Typical usage example:

  result = OpenAICompatibleBackendCheck('qwen', backend_configuration).run()
"""

import httpx

from trading_agent.configuration import agent_configuration
from trading_agent.doctor import doctor_check

_TIMEOUT_SECONDS = 3.0
_UNAUTHORIZED = 401


class OpenAICompatibleBackendCheck(doctor_check.DoctorCheck):
    """Checks one backend of kind "openai_compatible"."""

    def __init__(
        self,
        backend_name: str,
        backend_configuration: agent_configuration.BackendConfiguration,
    ):
        """Creates the check.

        Args:
            backend_name (str): The backend's name in trading_agent.toml.
            backend_configuration (agent_configuration.BackendConfiguration): Its settings.
        """
        self.name = f'Backend {backend_name} (OpenAI-compatible)'
        self._backend_configuration = backend_configuration

    def run(self) -> doctor_check.CheckResult:
        """Asks the server for its list of models.

        Returns:
            doctor_check.CheckResult: OK when it answers, a warning when it needs an API key, failed when it is unreachable.
        """
        base_url = self._backend_configuration.base_url
        try:
            response = httpx.get(f'{base_url}/models', timeout=_TIMEOUT_SECONDS)
        except httpx.HTTPError as error:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.FAILED,
                f'Server at {base_url} did not answer: {error!r}',
            )
        if response.status_code == _UNAUTHORIZED:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.WARNING,
                f'Server at {base_url} is running but needs an API key (added in milestone 4).',
            )
        if response.is_error:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.FAILED,
                f'Server at {base_url} answered HTTP {response.status_code}.',
            )
        return doctor_check.CheckResult(
            doctor_check.CheckStatus.OK,
            f'Server at {base_url} answered.',
        )
