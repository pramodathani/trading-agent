"""Checks that bwrap can start a sandbox, which the bash terminal needs.

Some Linux systems block the unprivileged namespaces bwrap uses, so the check starts a real, empty sandbox rather than only looking for the program.

Typical usage example:

  result = BubblewrapCheck().run()
"""

import shutil
import subprocess

from trading_agent.doctor import doctor_check

_TIMEOUT_SECONDS = 10.0


class BubblewrapCheck(doctor_check.DoctorCheck):
    """Checks the bwrap sandbox."""

    name = 'bwrap sandbox'

    def run(self) -> doctor_check.CheckResult:
        """Runs `true` inside a read-only bwrap sandbox.

        Returns:
            doctor_check.CheckResult: OK when the sandbox starts, failed otherwise.
        """
        bwrap_path = shutil.which('bwrap')
        if bwrap_path is None:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.FAILED,
                'bwrap is not installed; run: sudo apt install bubblewrap',
            )
        completed = subprocess.run(
            [
                bwrap_path,
                '--ro-bind',
                '/',
                '/',
                '--dev',
                '/dev',
                '--proc',
                '/proc',
                '--unshare-pid',
                'true',
            ],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            check=False,
        )
        if completed.returncode != 0:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.FAILED,
                f'bwrap could not start a sandbox: {completed.stderr.strip()}',
            )
        return doctor_check.CheckResult(
            doctor_check.CheckStatus.OK,
            'A test sandbox started and exited cleanly.',
        )
