"""The packages installed in workspace/shared/packages/, and what each one brings.

A package is one folder holding any of these:

  package.toml        optional: [package] name, description, version
  skills/             skills, used like the user's installed skills
  agents/             subagent definitions, used from milestone 14
  mcp_servers.json    MCP servers, added to the ones in the project's mcp_servers.json
  hooks/<event>/      hook scripts, run like the user's own hooks
  app.toml            a web page and a systemd unit, used from milestone 20

Everything is read in place from the package's folder, so removing a package is deleting its folder, and nothing of a package runs inside the gateway: its MCP servers and hooks are separate processes.

Typical usage example:

  packages = InstalledPackages(Path('workspace/shared/packages'))
  roots = packages.skill_roots()
"""

import dataclasses
import json
import tomllib
from pathlib import Path

MANIFEST_FILE_NAME = 'package.toml'
PARTS = (
    'skills',
    'agents',
    'mcp_servers.json',
    'hooks',
    'app.toml',
)


@dataclasses.dataclass(frozen=True)
class PackageSummary:
    """What one package contains.

    Attributes:
        name: The package's name, its folder name.
        description: Its description from package.toml, or an empty string.
        version: Its version from package.toml, or an empty string.
        skill_names: The folders under skills/ that hold a SKILL.md.
        agent_names: The Markdown files under agents/, without the suffix.
        mcp_server_names: The servers in its mcp_servers.json.
        hook_events: The event folders under hooks/.
        has_app: Whether it has an app.toml.
    """

    name: str
    description: str
    version: str
    skill_names: tuple[str, ...]
    agent_names: tuple[str, ...]
    mcp_server_names: tuple[str, ...]
    hook_events: tuple[str, ...]
    has_app: bool

    def describe(self) -> str:
        """Lists the package's contents in one line.

        Returns:
            str: Such as "2 skills (a, b); MCP servers: news; hooks for: order_placed".
        """
        parts = []
        if self.skill_names:
            parts.append(
                f'{len(self.skill_names)} skills ({", ".join(self.skill_names)})'
            )
        if self.agent_names:
            parts.append(f'subagents: {", ".join(self.agent_names)}')
        if self.mcp_server_names:
            parts.append(f'MCP servers: {", ".join(self.mcp_server_names)}')
        if self.hook_events:
            parts.append(f'hooks for: {", ".join(self.hook_events)}')
        if self.has_app:
            parts.append('a web app')
        return '; '.join(parts) or 'nothing usable'


class InstalledPackages:
    """Finds the installed packages and their parts."""

    def __init__(self, packages_directory: Path):
        """Describes the packages folder without reading it.

        Args:
            packages_directory (Path): workspace/shared/packages.
        """
        self.packages_directory = packages_directory

    def folders(self) -> list[Path]:
        """Every installed package's folder.

        Returns:
            list[Path]: The folders, sorted by name; hidden folders are skipped.
        """
        if not self.packages_directory.is_dir():
            return []
        folders = []
        for child in sorted(self.packages_directory.iterdir()):
            if child.is_dir() and not child.name.startswith('.'):
                folders.append(child)
        return folders

    def skill_roots(self) -> list[Path]:
        """The skills/ folders of every package that has one.

        Returns:
            list[Path]: The folders.
        """
        return self._existing('skills')

    def hook_roots(self) -> list[Path]:
        """The hooks/ folders of every package that has one.

        Returns:
            list[Path]: The folders.
        """
        return self._existing('hooks')

    def agent_roots(self) -> list[Path]:
        """The agents/ folders of every package that has one.

        Returns:
            list[Path]: The folders.
        """
        return self._existing('agents')

    def mcp_files(self) -> list[Path]:
        """The mcp_servers.json files of every package that has one.

        Returns:
            list[Path]: The files.
        """
        return self._existing('mcp_servers.json')

    def summary(self, folder: Path) -> PackageSummary:
        """Describes one package folder.

        Args:
            folder (Path): The package's folder, installed or not.

        Returns:
            PackageSummary: Its contents.
        """
        manifest = self.manifest(folder)
        skill_names = []
        skills = folder / 'skills'
        if skills.is_dir():
            for path in sorted(skills.glob('*/SKILL.md')):
                skill_names.append(path.parent.name)
        agent_names = []
        agents = folder / 'agents'
        if agents.is_dir():
            for path in sorted(agents.glob('*.md')):
                agent_names.append(path.stem)
        hook_events = []
        hooks = folder / 'hooks'
        if hooks.is_dir():
            for path in sorted(hooks.iterdir()):
                if path.is_dir():
                    hook_events.append(path.name)
        return PackageSummary(
            name=folder.name,
            description=str(manifest.get('description', '')),
            version=str(manifest.get('version', '')),
            skill_names=tuple(skill_names),
            agent_names=tuple(agent_names),
            mcp_server_names=tuple(self._mcp_server_names(folder)),
            hook_events=tuple(hook_events),
            has_app=(folder / 'app.toml').is_file(),
        )

    def manifest(self, folder: Path) -> dict:
        """Reads the [package] table of a folder's package.toml.

        Args:
            folder (Path): The package's folder.

        Returns:
            dict: The table, or an empty dictionary when there is no readable package.toml.
        """
        path = folder / MANIFEST_FILE_NAME
        if not path.is_file():
            return {}
        try:
            data = tomllib.loads(path.read_text(encoding='utf-8'))
        except tomllib.TOMLDecodeError:
            return {}
        table = data.get('package', {})
        if not isinstance(table, dict):
            return {}
        return table

    def _mcp_server_names(self, folder: Path) -> list[str]:
        """The server names in a package's mcp_servers.json.

        Args:
            folder (Path): The package's folder.

        Returns:
            list[str]: The names, or an empty list when the file is missing or unreadable.
        """
        path = folder / 'mcp_servers.json'
        if not path.is_file():
            return []
        try:
            servers = json.loads(path.read_text(encoding='utf-8')).get(
                'mcpServers', {}
            )
        except ValueError, AttributeError:
            return []
        if not isinstance(servers, dict):
            return []
        return list(servers)

    def _existing(self, part: str) -> list[Path]:
        """One part's path in every package that has it.

        Args:
            part (str): A folder or file name from PARTS.

        Returns:
            list[Path]: The existing paths.
        """
        paths = []
        for folder in self.folders():
            path = folder / part
            if path.exists():
                paths.append(path)
        return paths
