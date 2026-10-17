"""Lists each desk's own daily loss limit, or says plainly that only the account's limits apply.

Typical usage example:

  result = DeskLossLimitsCheck(layout.trading_rules_file, ['intraday']).run()
"""

from collections.abc import Sequence
from pathlib import Path

from trading_agent.doctor import doctor_check
from trading_agent.risk import trading_limits


class DeskLossLimitsCheck(doctor_check.DoctorCheck):
    """Reports the desks' daily loss limits."""

    name = 'Desk loss limits'

    def __init__(self, rules_file: Path, desk_names: Sequence[str]):
        """Creates the check.

        Args:
            rules_file (Path): TradingRules.md.
            desk_names (Sequence[str]): The desks.
        """
        self._rules_file = rules_file
        self._desk_names = list(desk_names)

    def run(self) -> doctor_check.CheckResult:
        """Reads the limits.

        Returns:
            doctor_check.CheckResult: OK with each desk's limit or the note that none is set; failed when the limits cannot be read.
        """
        try:
            limits = trading_limits.TradingLimitsReader(self._rules_file).read()
        except trading_limits.LimitsError as error:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.FAILED, str(error)
            )
        parts = []
        for desk_name in self._desk_names:
            desk = limits.desks.get(desk_name)
            if desk is not None and desk.daily_loss_limit_percent is not None:
                parts.append(f'{desk_name} {desk.daily_loss_limit_percent:g}%')
        account = limits.account
        account_text = f'the account stops at {account.daily_loss_limit_percent:g}% a day and {account.weekly_loss_limit_percent:g}% a week'
        if not parts:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.OK,
                f'No desk has its own limit (your choice on 17 October 2026); {account_text}.',
            )
        return doctor_check.CheckResult(
            doctor_check.CheckStatus.OK,
            f'{", ".join(parts)}; {account_text}.',
        )
