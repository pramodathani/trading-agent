"""The base class for one doctor check, and the result each check returns.

Typical usage example:

  result = check.run()
  print(result.status, result.message)
"""

import dataclasses
import enum


class CheckStatus(enum.StrEnum):
    """How a check turned out."""

    OK = 'ok'
    WARNING = 'warning'
    FAILED = 'failed'


@dataclasses.dataclass(frozen=True)
class CheckResult:
    """The outcome of one check.

    Attributes:
        status: Whether the check passed, passed with a warning, or failed.
        message: A sentence explaining the outcome and, if needed, how to fix it.
    """

    status: CheckStatus
    message: str


class DoctorCheck:
    """One thing the doctor checks. Subclasses provide the name and the check.

    Attributes:
        name: A short name shown in the doctor's report.
    """

    name = 'unnamed check'

    def run(self) -> CheckResult:
        """Runs the check.

        Returns:
            CheckResult: The outcome.

        Raises:
            NotImplementedError: Always, because subclasses must override this method.
        """
        raise NotImplementedError
