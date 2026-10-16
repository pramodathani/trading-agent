"""Where every file in the agent's workspace lives, and creating the missing ones from templates.

The workspace has a shared part that belongs to the user, and one folder per desk:

  workspace/
    shared/   Agents.md  User.md  TradingRules.md
    desks/<desk>/   Persona.md  Memory.md  proposals/  scratch/

Typical usage example:

  layout = WorkspaceLayout(Path('workspace'))
  layout.create_missing(['main'])
  text = layout.trading_rules_file.read_text()
"""

import importlib.resources
from collections.abc import Sequence
from pathlib import Path

SHARED_FILE_NAMES = (
    'Agents.md',
    'User.md',
    'TradingRules.md',
)
DESK_FILE_NAMES = (
    'Persona.md',
    'Memory.md',
)
USER_OWNED_FILE_NAMES = (
    'Agents.md',
    'User.md',
    'TradingRules.md',
    'Persona.md',
)
TEMPLATE_STATUS_LINE = 'Status: template, not filled in yet.'


class WorkspaceLayout:
    """The paths of one workspace.

    Attributes:
        root: The workspace folder.
        shared_directory: The folder of the files every desk shares.
        agents_file: The operating manual every desk follows.
        user_file: What the agent knows about the user.
        trading_rules_file: The strategies and hard limits.
    """

    def __init__(self, root: Path):
        """Describes a workspace without touching the disk.

        Args:
            root (Path): The workspace folder.
        """
        self.root = root
        self.shared_directory = root / 'shared'
        self.agents_file = self.shared_directory / 'Agents.md'
        self.user_file = self.shared_directory / 'User.md'
        self.trading_rules_file = self.shared_directory / 'TradingRules.md'

    @property
    def risk_ledger_file(self) -> Path:
        """The risk engine's SQLite ledger, shared by every desk."""
        return self.shared_directory / 'risk_ledger.db'

    def desk_directory(self, desk_name: str) -> Path:
        """The folder that belongs to one desk.

        Args:
            desk_name (str): The desk's name.

        Returns:
            Path: The desk's folder.
        """
        return self.root / 'desks' / desk_name

    def persona_file(self, desk_name: str) -> Path:
        """The desk's persona, which belongs to the user.

        Args:
            desk_name (str): The desk's name.

        Returns:
            Path: The desk's Persona.md.
        """
        return self.desk_directory(desk_name) / 'Persona.md'

    def memory_file(self, desk_name: str) -> Path:
        """The desk's lasting lessons, which the desk itself maintains.

        Args:
            desk_name (str): The desk's name.

        Returns:
            Path: The desk's Memory.md.
        """
        return self.desk_directory(desk_name) / 'Memory.md'

    def proposals_directory(self, desk_name: str) -> Path:
        """Where the desk's proposed changes to the user's files wait.

        Args:
            desk_name (str): The desk's name.

        Returns:
            Path: The desk's proposals folder.
        """
        return self.desk_directory(desk_name) / 'proposals'

    def scratch_directory(self, desk_name: str) -> Path:
        """The desk's working folder for temporary files.

        Args:
            desk_name (str): The desk's name.

        Returns:
            Path: The desk's scratch folder.
        """
        return self.desk_directory(desk_name) / 'scratch'

    def user_owned_file(self, desk_name: str, file_name: str) -> Path:
        """Finds one of the user's files by name.

        Args:
            desk_name (str): The desk whose Persona.md is meant, for that file name.
            file_name (str): One of USER_OWNED_FILE_NAMES.

        Returns:
            Path: The file's path.

        Raises:
            ValueError: The name is not one of the user's files.
        """
        if file_name == 'Persona.md':
            return self.persona_file(desk_name)
        if file_name in SHARED_FILE_NAMES:
            return self.shared_directory / file_name
        raise ValueError(f'Not one of the user files: {file_name!r}')

    def create_missing(self, desk_names: Sequence[str]) -> list[Path]:
        """Creates the folders, and writes each missing file from its template.

        Existing files are never overwritten.

        Args:
            desk_names (Sequence[str]): The desks to prepare.

        Returns:
            list[Path]: The files that were created.
        """
        created = []
        self.shared_directory.mkdir(parents=True, exist_ok=True)
        for file_name in SHARED_FILE_NAMES:
            target = self.shared_directory / file_name
            if self._write_template_if_missing(target, file_name):
                created.append(target)
        for desk_name in desk_names:
            self.proposals_directory(desk_name).mkdir(
                parents=True, exist_ok=True
            )
            self.scratch_directory(desk_name).mkdir(parents=True, exist_ok=True)
            for file_name in DESK_FILE_NAMES:
                target = self.desk_directory(desk_name) / file_name
                if self._write_template_if_missing(target, file_name):
                    created.append(target)
        return created

    def template_text(self, template_name: str) -> str:
        """Reads one of the templates shipped with the package.

        Args:
            template_name (str): The template's file name, such as "Agents.md".

        Returns:
            str: The template's text.
        """
        templates = (
            importlib.resources.files('trading_agent.workspace') / 'templates'
        )
        return (templates / template_name).read_text(encoding='utf-8')

    def is_template(self, path: Path) -> bool:
        """Says whether a file is still an unfilled template.

        Args:
            path (Path): The file.

        Returns:
            bool: True when the file is missing or still holds the template's status line.
        """
        if not path.is_file():
            return True
        return TEMPLATE_STATUS_LINE in path.read_text(encoding='utf-8')

    def _write_template_if_missing(
        self, target: Path, template_name: str
    ) -> bool:
        """Writes a template to a path that does not exist yet.

        Args:
            target (Path): Where the file belongs.
            template_name (str): The template to copy.

        Returns:
            bool: True when the file was written.
        """
        if target.exists():
            return False
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.template_text(template_name), encoding='utf-8')
        return True
