"""Routes for the user's files and the traders' proposals to change them.

  GET  /api/files                          every editable file: the shared files, each trader's Persona.md and Memory.md
  GET  /api/files/content?name=&trader=      one file's text
  PUT  /api/files/content                  replace one file's text
  GET  /api/proposals                      every proposal, with the change it would make
  POST /api/proposals/{id}/accept          apply a proposal, keeping a copy of the old file
  POST /api/proposals/{id}/reject          reject a proposal

The user may edit their own files and a trader's Memory.md. A trader's Memory.md is snapshotted first, as when the trader writes it. A new TradingRules.md is checked before it is saved: limits the risk engine could not read would stop every trader from opening positions, so such a version is refused.

Typical usage example:

  application.include_router(FileRoutes(guard, layout, parts, proposals).router())
"""

import logging
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import fastapi
import pydantic

from trading_agent.gateway import access_guard
from trading_agent.gateway import gateway_parts
from trading_agent.gateway.routes import route_group
from trading_agent.memory import checkpoints as checkpoints_module
from trading_agent.risk import trading_limits
from trading_agent.workspace import proposal_store as proposal_store_module
from trading_agent.workspace import workspace_layout

_LOGGER = logging.getLogger(__name__)
_MEMORY_FILE_NAME = 'Memory.md'


class FileWrite(pydantic.BaseModel):
    """The body of a file write.

    Attributes:
        name: The file's name, such as TradingRules.md or Persona.md.
        trader: The trader, for Persona.md and Memory.md.
        text: The complete new text.
    """

    name: str
    trader: str | None = None
    text: str


class FileRoutes(route_group.RouteGroup):
    """The file and proposal routes."""

    def __init__(
        self,
        guard: access_guard.AccessGuard,
        layout: workspace_layout.WorkspaceLayout,
        parts: Mapping[str, gateway_parts.TraderParts],
        proposals: proposal_store_module.ProposalStore,
    ):
        """Creates the routes.

        Args:
            guard (access_guard.AccessGuard): Checks the access token.
            layout (workspace_layout.WorkspaceLayout): Where the files are.
            parts (Mapping[str, gateway_parts.TraderParts]): Each trader's parts, for its checkpoints.
            proposals (proposal_store_module.ProposalStore): The proposals.
        """
        super().__init__(guard)
        self._layout = layout
        self._parts = parts
        self._proposals = proposals

    def _add_routes(self, router: fastapi.APIRouter) -> None:
        """Adds the file routes.

        Args:
            router (fastapi.APIRouter): The router.
        """
        router.add_api_route('/api/files', self.list_files, methods=['GET'])
        router.add_api_route(
            '/api/files/content', self.read_file, methods=['GET']
        )
        router.add_api_route(
            '/api/files/content', self.write_file, methods=['PUT']
        )
        router.add_api_route(
            '/api/proposals', self.list_proposals, methods=['GET']
        )
        router.add_api_route(
            '/api/proposals/{proposal_id}/accept', self.accept, methods=['POST']
        )
        router.add_api_route(
            '/api/proposals/{proposal_id}/reject', self.reject, methods=['POST']
        )

    def list_files(self) -> dict[str, Any]:
        """Every editable file.

        Returns:
            dict[str, Any]: Each file's name, trader (or None for shared files) and size in characters.
        """
        files = []
        for name in workspace_layout.SHARED_FILE_NAMES:
            files.append(self._file_entry(name, None))
        for trader_name in self._parts:
            files.append(self._file_entry('Persona.md', trader_name))
            files.append(self._file_entry(_MEMORY_FILE_NAME, trader_name))
        return {
            'files': files,
        }

    def read_file(self, name: str, trader: str | None = None) -> dict[str, Any]:
        """One file's text.

        Args:
            name (str): The file's name.
            trader (str | None): The trader, for Persona.md and Memory.md.

        Returns:
            dict[str, Any]: The name, trader and text; an empty text for a file not created yet.
        """
        path = self._path(name, trader)
        text = path.read_text(encoding='utf-8') if path.is_file() else ''
        return {
            'name': name,
            'trader': trader,
            'text': text,
        }

    def write_file(self, request: FileWrite) -> dict[str, Any]:
        """Replaces one file's text.

        Args:
            request (FileWrite): The file and its new text.

        Returns:
            dict[str, Any]: The name, trader and new size.

        Raises:
            fastapi.HTTPException: The new TradingRules.md cannot be read by the risk engine (status 400).
        """
        path = self._path(request.name, request.trader)
        if request.name == 'TradingRules.md':
            self._check_limits(request.text)
        if request.name == _MEMORY_FILE_NAME:
            parts = self._find(self._parts, request.trader or '', 'trader')
            try:
                parts.checkpoints.snapshot('before the user edited Memory.md')
            except checkpoints_module.CheckpointError:
                _LOGGER.exception(
                    'Could not snapshot before the user edited Memory.md'
                )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(request.text, encoding='utf-8')
        return {
            'name': request.name,
            'trader': request.trader,
            'characters': len(request.text),
        }

    def list_proposals(self) -> dict[str, Any]:
        """Every proposal, newest first, with the change each would make.

        Returns:
            dict[str, Any]: The proposals.
        """
        proposals = []
        for proposal in self._proposals.all():
            entry = proposal.to_json_dictionary()
            entry['difference'] = self._proposals.difference(
                proposal.proposal_id
            )
            proposals.append(entry)
        return {
            'proposals': proposals,
        }

    def accept(self, proposal_id: str) -> dict[str, Any]:
        """Applies a proposal.

        Args:
            proposal_id (str): The proposal.

        Returns:
            dict[str, Any]: The file that now holds the proposed text.

        Raises:
            fastapi.HTTPException: The proposal does not exist or is not pending (status 409).
        """
        try:
            target = self._proposals.accept(proposal_id)
        except proposal_store_module.ProposalError as error:
            raise fastapi.HTTPException(
                status_code=409, detail=str(error)
            ) from error
        return {
            'accepted': proposal_id,
            'file': str(target),
        }

    def reject(self, proposal_id: str) -> dict[str, Any]:
        """Rejects a proposal.

        Args:
            proposal_id (str): The proposal.

        Returns:
            dict[str, Any]: A confirmation.

        Raises:
            fastapi.HTTPException: The proposal does not exist or is not pending (status 409).
        """
        try:
            self._proposals.reject(proposal_id)
        except proposal_store_module.ProposalError as error:
            raise fastapi.HTTPException(
                status_code=409, detail=str(error)
            ) from error
        return {
            'rejected': proposal_id,
        }

    def _path(self, name: str, trader: str | None) -> Path:
        """The file a name and trader refer to.

        Args:
            name (str): The file's name.
            trader (str | None): The trader, for Persona.md and Memory.md.

        Returns:
            Path: The file.

        Raises:
            fastapi.HTTPException: The trader is unknown (status 404), or the name is not an editable file (status 400).
        """
        if name in ('Persona.md', _MEMORY_FILE_NAME):
            self._find(self._parts, trader or '', 'trader')
        if name == _MEMORY_FILE_NAME:
            return self._layout.memory_file(trader)
        try:
            return self._layout.user_owned_file(trader or '', name)
        except ValueError as error:
            raise fastapi.HTTPException(
                status_code=400, detail=str(error)
            ) from error

    def _file_entry(self, name: str, trader: str | None) -> dict[str, Any]:
        """One file in the list.

        Args:
            name (str): The file's name.
            trader (str | None): Its trader, or None.

        Returns:
            dict[str, Any]: The name, trader, whether it exists and its size.
        """
        path = self._path(name, trader)
        exists = path.is_file()
        return {
            'name': name,
            'trader': trader,
            'exists': exists,
            'characters': len(path.read_text(encoding='utf-8'))
            if exists
            else 0,
        }

    def _check_limits(self, text: str) -> None:
        """Checks that a new TradingRules.md has limits the risk engine can read.

        Args:
            text (str): The new text.

        Raises:
            fastapi.HTTPException: The limits block is missing or invalid (status 400).
        """
        with tempfile.TemporaryDirectory() as scratch:
            trial = Path(scratch) / 'TradingRules.md'
            trial.write_text(text, encoding='utf-8')
            try:
                trading_limits.TradingLimitsReader(trial).read()
            except trading_limits.LimitsError as error:
                raise fastapi.HTTPException(
                    status_code=400,
                    detail=f'Not saved: the risk engine could not read these limits ({error}), and would refuse every new position.',
                ) from error
