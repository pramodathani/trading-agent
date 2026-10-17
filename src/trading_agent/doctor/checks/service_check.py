"""Checks that trading-agent runs as a systemd user service, so it restarts after a crash and at every boot.

Typical usage example:

  result = ServiceCheck().run()
"""

import subprocess

from trading_agent.doctor import doctor_check

_UNIT = 'trading-agent.service'
_TIMEOUT_SECONDS = 10


class ServiceCheck(doctor_check.DoctorCheck):
    """Asks systemd whether the service is enabled and running."""

    name = 'Service'

    def run(self) -> doctor_check.CheckResult:
        """Asks systemctl --user is-enabled and is-active.

        Returns:
            doctor_check.CheckResult: OK when enabled and active; failed otherwise, with the commands that install it.
        """
        enabled = self._ask('is-enabled')
        active = self._ask('is-active')
        if enabled == 'enabled' and active == 'active':
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.OK,
                f'{_UNIT} is enabled and running; it restarts after a crash and starts at boot.',
            )
        return doctor_check.CheckResult(
            doctor_check.CheckStatus.FAILED,
            f'{_UNIT} is {enabled} and {active}. Install it with: systemctl --user link $PWD/deploy/{_UNIT} && systemctl --user enable --now {_UNIT}',
        )

    def _ask(self, question: str) -> str:
        """Runs one systemctl question.

        Args:
            question (str): "is-enabled" or "is-active".

        Returns:
            str: systemctl's one-word answer, such as "enabled", or "unknown" when it cannot be asked.
        """
        try:
            answer = subprocess.run(
                [
                    'systemctl',
                    '--user',
                    question,
                    _UNIT,
                ],
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_SECONDS,
                check=False,
            )
        except OSError, subprocess.TimeoutExpired:
            return 'unknown'
        return answer.stdout.strip() or 'unknown'
