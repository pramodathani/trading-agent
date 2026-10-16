"""Checks that Google Chrome is installed for the browser tools.

Typical usage example:

  result = ChromeCheck().run()
"""

import shutil
import subprocess

from trading_agent.doctor import doctor_check

_TIMEOUT_SECONDS = 10.0


class ChromeCheck(doctor_check.DoctorCheck):
    """Checks for the google-chrome program."""

    name = 'Google Chrome'

    def run(self) -> doctor_check.CheckResult:
        """Looks for google-chrome and asks it for its version.

        Returns:
            doctor_check.CheckResult: OK when Chrome is installed, failed otherwise.
        """
        chrome_path = shutil.which('google-chrome')
        if chrome_path is None:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.FAILED,
                'google-chrome is not on PATH.',
            )
        completed = subprocess.run(
            [
                chrome_path,
                '--version',
            ],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            check=False,
        )
        return doctor_check.CheckResult(
            doctor_check.CheckStatus.OK,
            completed.stdout.strip(),
        )
