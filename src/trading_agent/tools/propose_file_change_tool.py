"""A tool with which a desk proposes a change to one of the user's files.

The desk cannot edit the user's files. It sends the complete new text and a reason, and the user accepts or rejects it with `trading-agent proposals`.

Typical usage example:

  tool = ProposeFileChangeTool(store, 'main')
"""

from typing import Literal

import pydantic

from trading_agent.tools import tool
from trading_agent.workspace import proposal_store


class ProposeFileChangeArguments(pydantic.BaseModel):
    """The arguments of propose_file_change.

    Attributes:
        file_name: Which of the user's files to change.
        content: The complete new text of the file.
        reason: Why the change is needed, in one or two sentences.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    file_name: Literal['Agents.md', 'User.md', 'TradingRules.md', 'Persona.md']
    content: str = pydantic.Field(min_length=1)
    reason: str = pydantic.Field(min_length=1)


class ProposeFileChangeTool(tool.Tool):
    """Saves a proposed new version of one of the user's files."""

    name = 'propose_file_change'
    description = "Proposes a new version of one of the user's files (Agents.md, User.md, TradingRules.md, or this desk's Persona.md). Give the complete new text, not a fragment, and a short reason. Nothing changes until the user accepts the proposal."
    arguments_model = ProposeFileChangeArguments

    def __init__(self, store: proposal_store.ProposalStore, desk_name: str):
        """Creates the tool for one desk.

        Args:
            store (proposal_store.ProposalStore): Where proposals are saved.
            desk_name (str): The desk using the tool.
        """
        self._store = store
        self._desk_name = desk_name

    async def run(
        self, arguments: ProposeFileChangeArguments
    ) -> tool.ToolResult:
        """Saves the proposal.

        Args:
            arguments (ProposeFileChangeArguments): The file, its new text and the reason.

        Returns:
            tool.ToolResult: The new proposal's id and how the user accepts it.
        """
        proposal = self._store.create(
            self._desk_name,
            arguments.file_name,
            arguments.content,
            arguments.reason,
        )
        return tool.ToolResult.success(
            f'Saved proposal {proposal.proposal_id} for {arguments.file_name}. The user can review it with: trading-agent proposals show {proposal.proposal_id}, and accept it with: trading-agent proposals accept {proposal.proposal_id}'
        )
