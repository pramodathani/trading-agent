"""Checks that tradingmachine's settings file exists and UBI answers.

Any HTTP answer, even an error status, means UBI is running. Only a refused or timed-out connection counts as a failure.

Typical usage example:

  result = UnifiedBrokerInterfaceCheck(Path('/home/pramod/Projects/tradingmachine/.env')).run()
"""

from pathlib import Path

import httpx
from tradingmachine.utilities import (
    configuration as tradingmachine_configuration,
)

from trading_agent.doctor import doctor_check

_TIMEOUT_SECONDS = 3.0


class UnifiedBrokerInterfaceCheck(doctor_check.DoctorCheck):
    """Checks the route from the agent to UBI through tradingmachine."""

    name = 'UBI (through tradingmachine)'

    def __init__(self, environment_file: Path):
        """Creates the check.

        Args:
            environment_file (Path): The .env file tradingmachine reads its UBI address from.
        """
        self._environment_file = environment_file

    def run(self) -> doctor_check.CheckResult:
        """Reads UBI's address from tradingmachine and sends it one request.

        Returns:
            doctor_check.CheckResult: OK when UBI answers, failed when the settings file is missing or UBI cannot be reached.
        """
        if not self._environment_file.is_file():
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.FAILED,
                f'tradingmachine settings file not found: {self._environment_file}',
            )
        settings = tradingmachine_configuration.Configuration(
            environment_file=str(self._environment_file),
        )
        base_url = settings.ubi_base_url
        try:
            response = httpx.get(base_url, timeout=_TIMEOUT_SECONDS)
        except httpx.HTTPError as error:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.FAILED,
                f'UBI at {base_url} did not answer: {error!r}',
            )
        return doctor_check.CheckResult(
            doctor_check.CheckStatus.OK,
            f'UBI at {base_url} answered (HTTP {response.status_code}).',
        )
