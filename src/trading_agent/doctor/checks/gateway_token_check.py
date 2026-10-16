"""Checks that the gateway's access token is set and long enough.

Typical usage example:

  result = GatewayTokenCheck(secrets).run()
"""

from trading_agent.configuration import secrets as secrets_module
from trading_agent.doctor import doctor_check

_MINIMUM_LENGTH = 32


class GatewayTokenCheck(doctor_check.DoctorCheck):
    """Checks TRADING_AGENT_GATEWAY_ACCESS_TOKEN without revealing it."""

    name = 'Gateway access token'

    def __init__(self, secrets: secrets_module.Secrets):
        """Creates the check.

        Args:
            secrets (secrets_module.Secrets): The secrets read from the environment and .env.
        """
        self._secrets = secrets

    def run(self) -> doctor_check.CheckResult:
        """Checks that the token is present and at least 32 characters long.

        Returns:
            doctor_check.CheckResult: OK when it is, failed when it is missing or short.
        """
        token = self._secrets.gateway_access_token
        if not token:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.FAILED,
                'TRADING_AGENT_GATEWAY_ACCESS_TOKEN is not set in .env.',
            )
        if len(token) < _MINIMUM_LENGTH:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.FAILED,
                f'The access token is shorter than {_MINIMUM_LENGTH} characters.',
            )
        return doctor_check.CheckResult(
            doctor_check.CheckStatus.OK,
            f'Set ({len(token)} characters).',
        )
