"""Checks that the limits block of TradingRules.md can be read, and reports the main limits.

Typical usage example:

  result = TradingLimitsCheck(Path('workspace/shared/TradingRules.md')).run()
"""

from pathlib import Path

from trading_agent.doctor import doctor_check
from trading_agent.risk import trading_limits


class TradingLimitsCheck(doctor_check.DoctorCheck):
    """Checks the risk engine's limits."""

    name = 'Trading limits (TradingRules.md)'

    def __init__(self, rules_file: Path):
        """Creates the check.

        Args:
            rules_file (Path): The TradingRules.md file.
        """
        self._rules_file = rules_file

    def run(self) -> doctor_check.CheckResult:
        """Reads the limits block.

        Returns:
            doctor_check.CheckResult: OK with the main limits, a warning when trading is switched off, or failed when the block cannot be read, in which case the risk engine refuses every new position.
        """
        try:
            limits = trading_limits.TradingLimitsReader(self._rules_file).read()
        except trading_limits.LimitsError as error:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.FAILED,
                f'{error}; the risk engine will refuse every order that opens a position.',
            )
        account = limits.account
        summary = f'daily loss {account.daily_loss_limit_percent:g}%, weekly loss {account.weekly_loss_limit_percent:g}%, per order {account.maximum_order_value_percent:g}%, option writing {"allowed" if account.allow_option_writing else "forbidden"}'
        if not account.trading_enabled:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.WARNING,
                f'trading_enabled is false, so no position can be opened ({summary}).',
            )
        return doctor_check.CheckResult(
            doctor_check.CheckStatus.OK,
            f'Trading enabled; {summary}.',
        )
