"""Says whether orders are dry runs or live.

Typical usage example:

  result = TradingModeCheck('dry_run').run()
"""

from trading_agent.doctor import doctor_check


class TradingModeCheck(doctor_check.DoctorCheck):
    """Reports trading_agent.toml's mode."""

    name = 'Trading mode'

    def __init__(self, mode: str):
        """Creates the check.

        Args:
            mode (str): "dry_run" or "live".
        """
        self._mode = mode

    def run(self) -> doctor_check.CheckResult:
        """Reports the mode.

        Returns:
            doctor_check.CheckResult: OK when live; a warning in dry_run, which is the last switch to throw once everything else passes.
        """
        if self._mode == 'live':
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.OK,
                'LIVE: orders go to the brokers through UBI.',
            )
        return doctor_check.CheckResult(
            doctor_check.CheckStatus.WARNING,
            'dry_run: UBI checks every order and sends none. When everything else passes, set mode = "live" in trading_agent.toml and restart the service.',
        )
