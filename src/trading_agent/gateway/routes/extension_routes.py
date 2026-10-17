"""Routes for the extensions: skills, subagents, MCP servers, packages and checkpoints.

  GET  /api/desks/{desk}/skills                         the desk's usable skills with their usage, and the hidden ones
  GET  /api/subagents                                   the subagent definitions, and the files that could not be read
  GET  /api/mcp                                         each MCP server's state and tools
  GET  /api/packages                                    the installed packages
  GET  /api/desks/{desk}/checkpoints                    the snapshots of the desk's own files
  POST /api/desks/{desk}/checkpoints/{checkpoint}/restore  put the desk's files back as they were

Typical usage example:

  application.include_router(ExtensionRoutes(guard, parts, shared, manager).router())
"""

from collections.abc import Mapping
from typing import Any

import fastapi

from trading_agent.extensions import mcp_client_manager
from trading_agent.gateway import access_guard
from trading_agent.gateway import gateway_parts
from trading_agent.gateway.routes import route_group
from trading_agent.memory import checkpoints as checkpoints_module
from trading_agent.skills import skill_usage

_CHECKPOINT_PATTERN = '^[0-9a-f]{7,40}$'
_CHECKPOINTS_LISTED = 50


class ExtensionRoutes(route_group.RouteGroup):
    """The extension routes."""

    def __init__(
        self,
        guard: access_guard.AccessGuard,
        parts: Mapping[str, gateway_parts.DeskParts],
        shared: gateway_parts.SharedParts,
        manager: mcp_client_manager.McpClientManager,
    ):
        """Creates the routes.

        Args:
            guard (access_guard.AccessGuard): Checks the access token.
            parts (Mapping[str, gateway_parts.DeskParts]): Each desk's skills and checkpoints.
            shared (gateway_parts.SharedParts): The layout, subagents and packages.
            manager (mcp_client_manager.McpClientManager): The MCP connections.
        """
        super().__init__(guard)
        self._parts = parts
        self._shared = shared
        self._manager = manager

    def _add_routes(self, router: fastapi.APIRouter) -> None:
        """Adds the extension routes.

        Args:
            router (fastapi.APIRouter): The router.
        """
        router.add_api_route(
            '/api/desks/{desk_name}/skills', self.skills, methods=['GET']
        )
        router.add_api_route('/api/subagents', self.subagents, methods=['GET'])
        router.add_api_route('/api/mcp', self.mcp_servers, methods=['GET'])
        router.add_api_route('/api/packages', self.packages, methods=['GET'])
        router.add_api_route(
            '/api/desks/{desk_name}/checkpoints',
            self.checkpoints,
            methods=['GET'],
        )
        router.add_api_route(
            '/api/desks/{desk_name}/checkpoints/{checkpoint_id}/restore',
            self.restore_checkpoint,
            methods=['POST'],
        )

    def skills(self, desk_name: str) -> dict[str, Any]:
        """The desk's skills.

        Args:
            desk_name (str): The desk.

        Returns:
            dict[str, Any]: The usable skills with where they come from and how often they were used, and the hidden skills with what they miss.
        """
        parts = self._find(self._parts, desk_name, 'desk')
        statistics = skill_usage.SkillUsageReader(
            self._shared.layout.skill_usage_file(desk_name)
        ).statistics()
        available = []
        for skill in parts.skills.available():
            entry = {
                'name': skill.name,
                'description': skill.description,
                'origin': skill.origin,
                'uses': 0,
                'troubled_uses': 0,
                'last_used': None,
            }
            usage = statistics.get(skill.name)
            if usage is not None:
                entry['uses'] = usage.uses
                entry['troubled_uses'] = usage.troubled_uses
                entry['last_used'] = usage.last_used
            available.append(entry)
        hidden = []
        for hidden_skill in parts.skills.hidden():
            hidden.append(
                {
                    'name': hidden_skill.skill.name,
                    'description': hidden_skill.skill.description,
                    'origin': hidden_skill.skill.origin,
                    'missing': list(hidden_skill.missing),
                }
            )
        return {
            'available': available,
            'hidden': hidden,
        }

    def subagents(self) -> dict[str, Any]:
        """The subagent definitions.

        Returns:
            dict[str, Any]: Each definition's name, description, tools, models and limits, and the broken files with their errors.
        """
        definitions = []
        for definition in self._shared.subagents.definitions():
            definitions.append(
                {
                    'name': definition.name,
                    'description': definition.description,
                    'tools': list(definition.tool_names)
                    if definition.tool_names is not None
                    else None,
                    'models': list(definition.models)
                    if definition.models is not None
                    else None,
                    'maximum_turns': definition.maximum_turns,
                    'timeout_seconds': definition.timeout_seconds,
                    'path': str(definition.path),
                }
            )
        broken = []
        for broken_definition in self._shared.subagents.broken():
            broken.append(
                {
                    'path': str(broken_definition.path),
                    'error': broken_definition.error,
                }
            )
        return {
            'subagents': definitions,
            'broken': broken,
        }

    def mcp_servers(self) -> dict[str, Any]:
        """Each MCP server's state.

        Returns:
            dict[str, Any]: Each server's name, transport, state, error and tool names.
        """
        servers = []
        for name, connection in self._manager.connections.items():
            tool_names = []
            for tool in connection.tools:
                tool_names.append(tool.name)
            servers.append(
                {
                    'name': name,
                    'type': connection.configuration.type,
                    'state': connection.state,
                    'error': connection.error,
                    'tools': tool_names,
                }
            )
        return {
            'servers': servers,
        }

    def packages(self) -> dict[str, Any]:
        """The installed packages.

        Returns:
            dict[str, Any]: Each package's name, version, description and what it brought.
        """
        packages = []
        for folder in self._shared.packages.folders():
            summary = self._shared.packages.summary(folder)
            packages.append(
                {
                    'name': summary.name,
                    'version': summary.version,
                    'description': summary.description,
                    'skills': list(summary.skill_names),
                    'agents': list(summary.agent_names),
                    'mcp_servers': list(summary.mcp_server_names),
                    'hooks': list(summary.hook_events),
                    'has_app': summary.has_app,
                }
            )
        return {
            'packages': packages,
        }

    def checkpoints(self, desk_name: str) -> dict[str, Any]:
        """The desk's snapshots, newest first.

        Args:
            desk_name (str): The desk.

        Returns:
            dict[str, Any]: Each snapshot's identifier, time and reason.

        Raises:
            fastapi.HTTPException: git failed (status 500).
        """
        parts = self._find(self._parts, desk_name, 'desk')
        try:
            snapshots = parts.checkpoints.list(_CHECKPOINTS_LISTED)
        except checkpoints_module.CheckpointError as error:
            raise fastapi.HTTPException(
                status_code=500, detail=str(error)
            ) from error
        entries = []
        for snapshot in snapshots:
            entries.append(
                {
                    'checkpoint_id': snapshot.checkpoint_id,
                    'created_at': snapshot.created_at,
                    'reason': snapshot.reason,
                }
            )
        return {
            'checkpoints': entries,
        }

    def restore_checkpoint(
        self,
        desk_name: str,
        checkpoint_id: str = fastapi.Path(pattern=_CHECKPOINT_PATTERN),
    ) -> dict[str, Any]:
        """Restores the desk's files from a snapshot.

        Args:
            desk_name (str): The desk.
            checkpoint_id (str): The snapshot.

        Returns:
            dict[str, Any]: The restored checkpoint, and the snapshot taken just before restoring, which undoes the restore.

        Raises:
            fastapi.HTTPException: The snapshot could not be restored (status 400).
        """
        parts = self._find(self._parts, desk_name, 'desk')
        try:
            undo_checkpoint_id = parts.checkpoints.restore(checkpoint_id)
        except checkpoints_module.CheckpointError as error:
            raise fastapi.HTTPException(
                status_code=400, detail=str(error)
            ) from error
        return {
            'restored': checkpoint_id,
            'undo_checkpoint_id': undo_checkpoint_id,
        }
