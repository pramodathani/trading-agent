"""Checks that the agent runs on Python 3.14 or later.

Typical usage example:

  result = PythonVersionCheck().run()
"""

import sys

from trading_agent.doctor import doctor_check

_MINIMUM_VERSION = (
    3,
    14,
)


class PythonVersionCheck(doctor_check.DoctorCheck):
    """Checks the version of the running Python interpreter."""

    name = 'Python version'

    def run(self) -> doctor_check.CheckResult:
        """Compares the running version with the minimum.

        Returns:
            doctor_check.CheckResult: OK on 3.14 or later, failed otherwise.
        """
        version_text = '.'.join(str(part) for part in sys.version_info[:3])
        if sys.version_info[:2] >= _MINIMUM_VERSION:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.OK,
                f'Python {version_text}.',
            )
        return doctor_check.CheckResult(
            doctor_check.CheckStatus.FAILED,
            f'Python {version_text} is too old; 3.14 or later is needed.',
        )
