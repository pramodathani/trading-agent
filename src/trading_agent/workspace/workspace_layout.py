"""Where every file in the agent's workspace lives, and creating the missing ones from templates.

The workspace has a shared part that belongs to the user, and one folder per desk:

  workspace/
    shared/   Agents.md  User.md  TradingRules.md
    shared/skills/installed/   the user's imported skills
    shared/knowledge/   the user's documents, searched with search_knowledge
    shared/agents/   the user's subagent definitions, starting with four starters
    shared/hooks/<event>/   the user's hook scripts
    shared/packages/<package>/   installed packages
    desks/<desk>/   Persona.md  Memory.md  notes/  sessions/  skills/  proposals/  scratch/
    .checkpoints/<desk>.git   snapshots of each desk's own files

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

    @property
    def desk_orders_file(self) -> Path:
        """The SQLite record of which desk placed which order."""
        return self.shared_directory / 'desk_orders.db'

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

    @property
    def agents_directory(self) -> Path:
        """The user's subagent definitions, one Markdown file each."""
        return self.shared_directory / 'agents'

    @property
    def hooks_directory(self) -> Path:
        """The user's hook scripts, one folder per event."""
        return self.shared_directory / 'hooks'

    @property
    def packages_directory(self) -> Path:
        """The installed packages, one folder each."""
        return self.shared_directory / 'packages'

    @property
    def knowledge_directory(self) -> Path:
        """The user's documents that every desk can search."""
        return self.shared_directory / 'knowledge'

    @property
    def knowledge_index_file(self) -> Path:
        """The SQLite full-text index of the knowledge folder."""
        return self.shared_directory / 'knowledge.db'

    @property
    def installed_skills_directory(self) -> Path:
        """The user's imported skills, shared by every desk and read-only to them."""
        return self.shared_directory / 'skills' / 'installed'

    def agent_skills_directory(self, desk_name: str) -> Path:
        """The skills the desk wrote for itself.

        Args:
            desk_name (str): The desk's name.

        Returns:
            Path: The desk's skills/agent folder.
        """
        return self.desk_directory(desk_name) / 'skills' / 'agent'

    def skill_usage_file(self, desk_name: str) -> Path:
        """The record of each time the desk loaded a skill.

        Args:
            desk_name (str): The desk's name.

        Returns:
            Path: The desk's skills/usage.jsonl.
        """
        return self.desk_directory(desk_name) / 'skills' / 'usage.jsonl'

    def skill_ledger_file(self, desk_name: str) -> Path:
        """The record of every change to the desk's own skills.

        Args:
            desk_name (str): The desk's name.

        Returns:
            Path: The desk's skills/ledger.jsonl.
        """
        return self.desk_directory(desk_name) / 'skills' / 'ledger.jsonl'

    def notes_directory(self, desk_name: str) -> Path:
        """Where the desk records its daily improvement notes.

        Args:
            desk_name (str): The desk's name.

        Returns:
            Path: The desk's notes folder.
        """
        return self.desk_directory(desk_name) / 'notes'

    def sessions_directory(self, desk_name: str) -> Path:
        """Where the desk's session logs, session state and daily summaries are kept.

        Args:
            desk_name (str): The desk's name.

        Returns:
            Path: The desk's sessions folder.
        """
        return self.desk_directory(desk_name) / 'sessions'

    def checkpoint_repository(self, desk_name: str) -> Path:
        """The git directory holding snapshots of the desk's own files.

        Args:
            desk_name (str): The desk's name.

        Returns:
            Path: The repository, such as workspace/.checkpoints/main.git.
        """
        return self.root / '.checkpoints' / f'{desk_name}.git'

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

        Existing files are never overwritten. The starter subagents are written only when the agents folder does not exist yet, so one the user deleted stays deleted.

        Args:
            desk_names (Sequence[str]): The desks to prepare.

        Returns:
            list[Path]: The files that were created.
        """
        created = []
        self.shared_directory.mkdir(parents=True, exist_ok=True)
        self.knowledge_directory.mkdir(parents=True, exist_ok=True)
        for file_name in SHARED_FILE_NAMES:
            target = self.shared_directory / file_name
            if self._write_template_if_missing(target, file_name):
                created.append(target)
        if not self.agents_directory.exists():
            created.extend(self._write_starter_agents())
        for desk_name in desk_names:
            self.proposals_directory(desk_name).mkdir(
                parents=True, exist_ok=True
            )
            self.scratch_directory(desk_name).mkdir(parents=True, exist_ok=True)
            self.notes_directory(desk_name).mkdir(parents=True, exist_ok=True)
            for file_name in DESK_FILE_NAMES:
                target = self.desk_directory(desk_name) / file_name
                if self._write_template_if_missing(target, file_name):
                    created.append(target)
        return created

    def _write_starter_agents(self) -> list[Path]:
        """Copies the starter subagent definitions into the new agents folder.

        Returns:
            list[Path]: The files written.
        """
        templates = (
            importlib.resources.files('trading_agent.workspace')
            / 'templates'
            / 'agents'
        )
        self.agents_directory.mkdir(parents=True)
        written = []
        for template in sorted(templates.iterdir(), key=lambda item: item.name):
            if not template.name.endswith('.md'):
                continue
            target = self.agents_directory / template.name
            target.write_text(
                template.read_text(encoding='utf-8'), encoding='utf-8'
            )
            written.append(target)
        return written

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
