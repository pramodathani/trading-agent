"""Checks that the risk engine has refused a desk because another desk owned the stock, outside the tests.

Typical usage example:

  result = OwnershipConflictCheck(search).run()
"""

from trading_agent.doctor import doctor_check
from trading_agent.doctor.checks import journal_search as journal_search_module

_OWNED_WORDS = 'belongs to'


class OwnershipConflictCheck(doctor_check.DoctorCheck):
    """Looks in the journals for a refusal over stock ownership."""

    name = 'Desks sharing a stock'

    def __init__(self, search: journal_search_module.JournalSearch):
        """Creates the check.

        Args:
            search (journal_search_module.JournalSearch): Searches the desks' journals.
        """
        self._search = search

    def run(self) -> doctor_check.CheckResult:
        """Finds the latest ownership refusal.

        Returns:
            doctor_check.CheckResult: OK when one was seen; a warning otherwise, because the unit tests cover it but it has not been seen with UBI.
        """
        for event in self._search.events('risk_decision'):
            payload = event.get('payload', {})
            reasons = ' '.join(
                str(reason) for reason in payload.get('reasons', [])
            )
            if not payload.get('approved') and _OWNED_WORDS in reasons:
                return doctor_check.CheckResult(
                    doctor_check.CheckStatus.OK,
                    f'The risk engine refused {event.get("desk")} at {event.get("created_at", "")[:16]}: {reasons}',
                )
        return doctor_check.CheckResult(
            doctor_check.CheckStatus.WARNING,
            'Not yet seen with UBI (the tests cover it). On a trading day, have one desk buy a stock in dry run, then ask another desk to buy the same stock; the second must be refused.',
        )
