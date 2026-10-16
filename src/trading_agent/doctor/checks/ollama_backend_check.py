"""Checks that an Ollama backend's server answers and has the model.

Typical usage example:

  result = OllamaBackendCheck('gemma', backend_configuration).run()
"""

import httpx

from trading_agent.configuration import agent_configuration
from trading_agent.doctor import doctor_check

_TIMEOUT_SECONDS = 3.0


class OllamaBackendCheck(doctor_check.DoctorCheck):
    """Checks one backend of kind "ollama"."""

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
        self.name = f'Backend {backend_name} (Ollama)'
        self._backend_configuration = backend_configuration

    def run(self) -> doctor_check.CheckResult:
        """Lists Ollama's installed models and looks for the configured one.

        Returns:
            doctor_check.CheckResult: OK when the model is installed, failed when Ollama is unreachable or lacks the model.
        """
        base_url = self._backend_configuration.base_url
        model = self._backend_configuration.model
        try:
            response = httpx.get(
                f'{base_url}/api/tags', timeout=_TIMEOUT_SECONDS
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.FAILED,
                f'Ollama at {base_url} did not answer: {error!r}',
            )
        installed_models = []
        for entry in response.json().get('models', []):
            installed_models.append(entry.get('name'))
        if model not in installed_models:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.FAILED,
                f'Model {model} is not installed; run: ollama pull {model}',
            )
        return doctor_check.CheckResult(
            doctor_check.CheckStatus.OK,
            f'{model} is installed at {base_url}.',
        )
