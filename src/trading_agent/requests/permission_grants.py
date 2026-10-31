"""The user's standing permissions: a trader may use a tool that normally needs permission, until the user revokes it.

A grant is made by "Always allow" on a permission request, and is kept in workspace/shared/permission_grants.json.

Typical usage example:

  grants = PermissionGrants(layout)
  grants.grant('main', 'flatten_trader')
  grants.allows('main', 'flatten_trader')
"""

import dataclasses
import datetime
import json
from typing import Any

from trading_agent.workspace import workspace_layout


@dataclasses.dataclass(frozen=True)
class PermissionGrant:
    """One standing permission.

    Attributes:
        trader: The trader allowed.
        tool_name: The tool it may use without asking.
        granted_at: When the user granted it, as ISO 8601 text in UTC.
    """

    trader: str
    tool_name: str
    granted_at: str


class PermissionGrants:
    """Reads, adds and revokes standing permissions."""

    def __init__(self, layout: workspace_layout.WorkspaceLayout):
        """Creates the store.

        Args:
            layout (workspace_layout.WorkspaceLayout): The workspace whose shared folder holds the grants file.
        """
        self._path = layout.shared_directory / 'permission_grants.json'

    def all(self) -> list[PermissionGrant]:
        """Every standing permission, oldest first.

        Returns:
            list[PermissionGrant]: The grants.
        """
        if not self._path.is_file():
            return []
        grants = []
        for entry in json.loads(self._path.read_text(encoding='utf-8')):
            grants.append(PermissionGrant(**entry))
        return grants

    def allows(self, trader: str, tool_name: str) -> bool:
        """Says whether a trader may use a tool without asking.

        Args:
            trader (str): The trader.
            tool_name (str): The tool.

        Returns:
            bool: True when the user granted it.
        """
        for grant in self.all():
            if grant.trader == trader and grant.tool_name == tool_name:
                return True
        return False

    def grant(self, trader: str, tool_name: str) -> PermissionGrant:
        """Lets a trader use a tool without asking from now on.

        Args:
            trader (str): The trader.
            tool_name (str): The tool.

        Returns:
            PermissionGrant: The grant, or the existing one.
        """
        grants = self.all()
        for existing in grants:
            if existing.trader == trader and existing.tool_name == tool_name:
                return existing
        grant = PermissionGrant(
            trader=trader,
            tool_name=tool_name,
            granted_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )
        grants.append(grant)
        self._write(grants)
        return grant

    def revoke(self, trader: str, tool_name: str) -> bool:
        """Makes a trader ask again before using a tool.

        Args:
            trader (str): The trader.
            tool_name (str): The tool.

        Returns:
            bool: True when a grant was removed, False when there was none.
        """
        grants = self.all()
        kept = []
        for grant in grants:
            if grant.trader != trader or grant.tool_name != tool_name:
                kept.append(grant)
        if len(kept) == len(grants):
            return False
        self._write(kept)
        return True

    def _write(self, grants: list[PermissionGrant]) -> None:
        """Saves the grants.

        Args:
            grants (list[PermissionGrant]): Every grant to keep.
        """
        entries: list[dict[str, Any]] = []
        for grant in grants:
            entries.append(dataclasses.asdict(grant))
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(entries, indent=2), encoding='utf-8')
