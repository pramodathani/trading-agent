"""Proposed changes to the user's files, waiting for the user to accept or reject them.

The agent cannot edit Agents.md, User.md, TradingRules.md or a Persona.md. It writes a proposal instead: the complete new text of one file and the reason. Accepting a proposal keeps a copy of the file it replaces.

Typical usage example:

  store = ProposalStore(layout)
  proposal = store.create('main', 'User.md', new_text, 'Filled in from the interview')
  store.accept(proposal.proposal_id)
"""

import dataclasses
import datetime
import difflib
import json
import uuid
from pathlib import Path
from typing import Any, Self

from trading_agent.workspace import workspace_layout

_PENDING = 'pending'
_ACCEPTED = 'accepted'
_REJECTED = 'rejected'


class ProposalError(ValueError):
    """A proposal does not exist, or is not pending."""


@dataclasses.dataclass(frozen=True)
class Proposal:
    """One proposed change.

    Attributes:
        proposal_id: The identifier the user types to accept or reject it.
        desk: The desk that proposed it.
        file_name: The user file it would replace.
        content: The complete new text.
        reason: Why the desk proposes it.
        created_at: When it was proposed, as ISO 8601 text in UTC.
        status: "pending", "accepted" or "rejected".
    """

    proposal_id: str
    desk: str
    file_name: str
    content: str
    reason: str
    created_at: str
    status: str

    @classmethod
    def from_json_dictionary(cls, dictionary: dict[str, Any]) -> Self:
        """Reads a proposal saved by to_json_dictionary.

        Args:
            dictionary (dict[str, Any]): The saved fields.

        Returns:
            Proposal: The proposal.
        """
        return cls(**dictionary)

    def to_json_dictionary(self) -> dict[str, Any]:
        """Converts the proposal to a dictionary that json.dumps can write.

        Returns:
            dict[str, Any]: Every field.
        """
        return dataclasses.asdict(self)


class ProposalStore:
    """Saves, lists, accepts and rejects proposals."""

    def __init__(self, layout: workspace_layout.WorkspaceLayout):
        """Creates the store.

        Args:
            layout (workspace_layout.WorkspaceLayout): The workspace whose desks' proposals folders hold the proposals.
        """
        self._layout = layout

    def create(
        self,
        desk_name: str,
        file_name: str,
        content: str,
        reason: str,
    ) -> Proposal:
        """Saves a new pending proposal.

        Args:
            desk_name (str): The desk proposing the change.
            file_name (str): One of the user's files.
            content (str): The complete new text.
            reason (str): Why.

        Returns:
            Proposal: The saved proposal.

        Raises:
            ValueError: The file is not one of the user's files.
        """
        self._layout.user_owned_file(desk_name, file_name)
        now = datetime.datetime.now(datetime.UTC)
        proposal = Proposal(
            proposal_id=f'{now:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}',
            desk=desk_name,
            file_name=file_name,
            content=content,
            reason=reason,
            created_at=now.isoformat(),
            status=_PENDING,
        )
        self._save(proposal)
        return proposal

    def all(self) -> list[Proposal]:
        """Every proposal from every desk, oldest first.

        Returns:
            list[Proposal]: The proposals.
        """
        proposals = []
        for path in sorted(self._layout.root.glob('desks/*/proposals/*.json')):
            dictionary = json.loads(path.read_text(encoding='utf-8'))
            proposals.append(Proposal.from_json_dictionary(dictionary))
        proposals.sort(key=lambda proposal: proposal.created_at)
        return proposals

    def get(self, proposal_id: str) -> Proposal:
        """Finds one proposal.

        Args:
            proposal_id (str): Its identifier.

        Returns:
            Proposal: The proposal.

        Raises:
            ProposalError: No proposal has that identifier.
        """
        for proposal in self.all():
            if proposal.proposal_id == proposal_id:
                return proposal
        raise ProposalError(f'No proposal with id {proposal_id!r}')

    def difference(self, proposal_id: str) -> str:
        """Shows what accepting a proposal would change, as a unified diff.

        Args:
            proposal_id (str): Its identifier.

        Returns:
            str: The diff, with "-" lines removed and "+" lines added.
        """
        proposal = self.get(proposal_id)
        target = self._layout.user_owned_file(proposal.desk, proposal.file_name)
        current = ''
        if target.is_file():
            current = target.read_text(encoding='utf-8')
        lines = difflib.unified_diff(
            current.splitlines(keepends=True),
            proposal.content.splitlines(keepends=True),
            fromfile=f'{proposal.file_name} (now)',
            tofile=f'{proposal.file_name} (proposed)',
        )
        return ''.join(lines)

    def accept(self, proposal_id: str) -> Path:
        """Replaces the user file with the proposed text, keeping a copy of the old one.

        Args:
            proposal_id (str): Its identifier.

        Returns:
            Path: The file that was replaced.

        Raises:
            ProposalError: The proposal does not exist or is not pending.
        """
        proposal = self._pending(proposal_id)
        target = self._layout.user_owned_file(proposal.desk, proposal.file_name)
        if target.is_file():
            backup = (
                self._layout.proposals_directory(proposal.desk)
                / 'replaced'
                / f'{proposal.proposal_id}-{proposal.file_name}'
            )
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_text(
                target.read_text(encoding='utf-8'), encoding='utf-8'
            )
        target.write_text(proposal.content, encoding='utf-8')
        self._save(dataclasses.replace(proposal, status=_ACCEPTED))
        return target

    def reject(self, proposal_id: str) -> None:
        """Marks a proposal as rejected without changing any file.

        Args:
            proposal_id (str): Its identifier.

        Raises:
            ProposalError: The proposal does not exist or is not pending.
        """
        proposal = self._pending(proposal_id)
        self._save(dataclasses.replace(proposal, status=_REJECTED))

    def _pending(self, proposal_id: str) -> Proposal:
        """Finds a proposal that is still waiting.

        Args:
            proposal_id (str): Its identifier.

        Returns:
            Proposal: The proposal.

        Raises:
            ProposalError: It does not exist or was already accepted or rejected.
        """
        proposal = self.get(proposal_id)
        if proposal.status != _PENDING:
            raise ProposalError(
                f'Proposal {proposal_id} is already {proposal.status}'
            )
        return proposal

    def _save(self, proposal: Proposal) -> None:
        """Writes a proposal to its desk's proposals folder.

        Args:
            proposal (Proposal): The proposal.
        """
        directory = self._layout.proposals_directory(proposal.desk)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f'{proposal.proposal_id}.json'
        path.write_text(
            json.dumps(proposal.to_json_dictionary(), indent=2),
            encoding='utf-8',
        )
