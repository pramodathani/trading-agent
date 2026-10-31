"""The `trading-agent proposals` commands: list, show, accept and reject.

Typical usage example:

  exit_code = ProposalCommands(store).run('list', None)
"""

import sys
from typing import TextIO

from trading_agent.workspace import proposal_store


class ProposalCommands:
    """Prints and changes proposals for the user."""

    def __init__(
        self,
        store: proposal_store.ProposalStore,
        output: TextIO = sys.stdout,
    ):
        """Creates the commands.

        Args:
            store (proposal_store.ProposalStore): Where the proposals are.
            output (TextIO): Where to print.
        """
        self._store = store
        self._output = output

    def run(self, action: str, proposal_id: str | None) -> int:
        """Runs one action.

        Args:
            action (str): "list", "show", "accept" or "reject".
            proposal_id (str | None): The proposal, for every action except "list".

        Returns:
            int: 0 on success, 1 when the proposal does not exist or is not pending.
        """
        try:
            if action == 'list':
                self._list()
            elif action == 'show':
                self._show(proposal_id)
            elif action == 'accept':
                target = self._store.accept(proposal_id)
                self._print(
                    f"Accepted {proposal_id}: {target} now holds the proposed text. The previous version is in the trader's proposals/replaced folder."
                )
            elif action == 'reject':
                self._store.reject(proposal_id)
                self._print(f'Rejected {proposal_id}. No file was changed.')
        except proposal_store.ProposalError as error:
            self._print(str(error))
            return 1
        return 0

    def _list(self) -> None:
        """Prints one line per proposal."""
        proposals = self._store.all()
        if not proposals:
            self._print('No proposals.')
            return
        for proposal in proposals:
            self._print(
                f'{proposal.proposal_id}  {proposal.status:8}  {proposal.trader:10}  {proposal.file_name:16}  {proposal.reason}'
            )

    def _show(self, proposal_id: str) -> None:
        """Prints a proposal's reason and what it would change.

        Args:
            proposal_id (str): The proposal.
        """
        proposal = self._store.get(proposal_id)
        self._print(
            f'{proposal.proposal_id} ({proposal.status}) from trader {proposal.trader} for {proposal.file_name}'
        )
        self._print(f'Reason: {proposal.reason}')
        self._print('')
        self._print(self._store.difference(proposal_id) or '(no change)')

    def _print(self, line: str) -> None:
        """Prints one line.

        Args:
            line (str): The line.
        """
        print(line, file=self._output)
