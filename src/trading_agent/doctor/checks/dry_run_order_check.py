"""Checks that at least one trader order has gone all the way through UBI's dry run.

UBI refuses even dry-run orders when the market's instrument list is not loaded, such as at weekends, so this can only pass after a trading day.

Typical usage example:

  result = DryRunOrderCheck(search).run()
"""

from trading_agent.doctor import doctor_check
from trading_agent.doctor.checks import journal_search as journal_search_module

_PLACED = 'placed'


class DryRunOrderCheck(doctor_check.DoctorCheck):
    """Looks in the journals for a placed dry-run order."""

    name = 'Dry-run order through UBI'

    def __init__(self, search: journal_search_module.JournalSearch):
        """Creates the check.

        Args:
            search (journal_search_module.JournalSearch): Searches the traders' journals.
        """
        self._search = search

    def run(self) -> doctor_check.CheckResult:
        """Finds the latest placed order.

        Returns:
            doctor_check.CheckResult: OK naming the latest placed dry-run order; failed when no order has been placed yet.
        """
        for event in self._search.events('order'):
            payload = event.get('payload', {})
            if payload.get('action') == _PLACED:
                mode = 'dry run' if payload.get('dry_run') else 'live'
                return doctor_check.CheckResult(
                    doctor_check.CheckStatus.OK,
                    f'{event.get("trader")} placed an order ({mode}) at {event.get("created_at", "")[:16]}.',
                )
        return doctor_check.CheckResult(
            doctor_check.CheckStatus.FAILED,
            'No order has gone through UBI yet. On a trading day, ask a trader in the chat to place one small dry-run order, such as buying 1 share of a cheap stock.',
        )
