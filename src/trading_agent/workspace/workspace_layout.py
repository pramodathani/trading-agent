"""Where every file in the agent's workspace lives, and creating the missing ones from templates.

The workspace has a shared part that belongs to the user, and one folder per trader:

  workspace/
    shared/   Agents.md  User.md  TradingRules.md
    shared/skills/installed/   the user's imported skills
    shared/knowledge/   the user's documents, searched with search_knowledge
    shared/agents/   the user's subagent definitions, starting with four starters
    shared/hooks/<event>/   the user's hook scripts
    shared/packages/<package>/   installed packages
    traders/<trader>/   Persona.md  Memory.md  notes/  sessions/  skills/  proposals/  requests/  scratch/  uploads/
    .checkpoints/<trader>.git   snapshots of each trader's own files

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
TRADER_FILE_NAMES = (
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
        shared_directory: The folder of the files every trader shares.
        agents_file: The operating manual every trader follows.
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
        """The risk engine's SQLite ledger, shared by every trader."""
        return self.shared_directory / 'risk_ledger.db'

    @property
    def trader_orders_file(self) -> Path:
        """The SQLite record of which trader placed which order."""
        return self.shared_directory / 'trader_orders.db'

    def trader_directory(self, trader_name: str) -> Path:
        """The folder that belongs to one trader.

        Args:
            trader_name (str): The trader's name.

        Returns:
            Path: The trader's folder.
        """
        return self.traders_directory / trader_name

    @property
    def traders_directory(self) -> Path:
        """The folder holding one folder per trader."""
        return self.root / 'traders'

    def trader_file(self, trader_name: str) -> Path:
        """The trader's record: its mandate, models, schedule and whether it is retired.

        Args:
            trader_name (str): The trader's name.

        Returns:
            Path: The trader's trader.toml.
        """
        return self.trader_directory(trader_name) / 'trader.toml'

    def persona_file(self, trader_name: str) -> Path:
        """The trader's persona, which belongs to the user.

        Args:
            trader_name (str): The trader's name.

        Returns:
            Path: The trader's Persona.md.
        """
        return self.trader_directory(trader_name) / 'Persona.md'

    def memory_file(self, trader_name: str) -> Path:
        """The trader's lasting lessons, which the trader itself maintains.

        Args:
            trader_name (str): The trader's name.

        Returns:
            Path: The trader's Memory.md.
        """
        return self.trader_directory(trader_name) / 'Memory.md'

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
        """The user's documents that every trader can search."""
        return self.shared_directory / 'knowledge'

    @property
    def knowledge_index_file(self) -> Path:
        """The SQLite full-text index of the knowledge folder."""
        return self.shared_directory / 'knowledge.db'

    @property
    def installed_skills_directory(self) -> Path:
        """The user's imported skills, shared by every trader and read-only to them."""
        return self.shared_directory / 'skills' / 'installed'

    def agent_skills_directory(self, trader_name: str) -> Path:
        """The skills the trader wrote for itself.

        Args:
            trader_name (str): The trader's name.

        Returns:
            Path: The trader's skills/agent folder.
        """
        return self.trader_directory(trader_name) / 'skills' / 'agent'

    def skill_usage_file(self, trader_name: str) -> Path:
        """The record of each time the trader loaded a skill.

        Args:
            trader_name (str): The trader's name.

        Returns:
            Path: The trader's skills/usage.jsonl.
        """
        return self.trader_directory(trader_name) / 'skills' / 'usage.jsonl'

    def skill_ledger_file(self, trader_name: str) -> Path:
        """The record of every change to the trader's own skills.

        Args:
            trader_name (str): The trader's name.

        Returns:
            Path: The trader's skills/ledger.jsonl.
        """
        return self.trader_directory(trader_name) / 'skills' / 'ledger.jsonl'

    def notes_directory(self, trader_name: str) -> Path:
        """Where the trader records its daily improvement notes.

        Args:
            trader_name (str): The trader's name.

        Returns:
            Path: The trader's notes folder.
        """
        return self.trader_directory(trader_name) / 'notes'

    def alerts_file(self, trader_name: str) -> Path:
        """The trader's price alerts.

        Args:
            trader_name (str): The trader's name.

        Returns:
            Path: The trader's alerts.json.
        """
        return self.trader_directory(trader_name) / 'alerts.json'

    @property
    def market_watcher_state_file(self) -> Path:
        """The ids of broker orders the market watcher has already reported."""
        return self.shared_directory / 'market_watcher.json'

    @property
    def telegram_pairing_file(self) -> Path:
        """The Telegram chats allowed to command the traders, and the pairing codes waiting for approval."""
        return self.shared_directory / 'telegram_pairing.json'

    @property
    def phone_devices_file(self) -> Path:
        """The phones running the Android app that receive push notifications."""
        return self.shared_directory / 'phone_devices.json'

    def cron_directory(self, trader_name: str) -> Path:
        """Where the trader's scheduled jobs and their run record are kept.

        Args:
            trader_name (str): The trader's name.

        Returns:
            Path: The trader's cron folder.
        """
        return self.trader_directory(trader_name) / 'cron'

    def sessions_directory(self, trader_name: str) -> Path:
        """Where the trader's session logs, session state and daily summaries are kept.

        Args:
            trader_name (str): The trader's name.

        Returns:
            Path: The trader's sessions folder.
        """
        return self.trader_directory(trader_name) / 'sessions'

    def checkpoint_repository(self, trader_name: str) -> Path:
        """The git directory holding snapshots of the trader's own files.

        Args:
            trader_name (str): The trader's name.

        Returns:
            Path: The repository, such as workspace/.checkpoints/main.git.
        """
        return self.root / '.checkpoints' / f'{trader_name}.git'

    def proposals_directory(self, trader_name: str) -> Path:
        """Where the trader's proposed changes to the user's files wait.

        Args:
            trader_name (str): The trader's name.

        Returns:
            Path: The trader's proposals folder.
        """
        return self.trader_directory(trader_name) / 'proposals'

    def requests_directory(self, trader_name: str) -> Path:
        """Where the trader's questions, plans and permission requests to the user are kept.

        Args:
            trader_name (str): The trader's name.

        Returns:
            Path: The trader's requests folder.
        """
        return self.trader_directory(trader_name) / 'requests'

    def scratch_directory(self, trader_name: str) -> Path:
        """The trader's working folder for temporary files.

        Args:
            trader_name (str): The trader's name.

        Returns:
            Path: The trader's scratch folder.
        """
        return self.trader_directory(trader_name) / 'scratch'

    def uploads_directory(self, trader_name: str) -> Path:
        """The trader's folder of files the user sent with messages.

        Args:
            trader_name (str): The trader's name.

        Returns:
            Path: The trader's uploads folder.
        """
        return self.trader_directory(trader_name) / 'uploads'

    def user_owned_file(self, trader_name: str, file_name: str) -> Path:
        """Finds one of the user's files by name.

        Args:
            trader_name (str): The trader whose Persona.md is meant, for that file name.
            file_name (str): One of USER_OWNED_FILE_NAMES.

        Returns:
            Path: The file's path.

        Raises:
            ValueError: The name is not one of the user's files.
        """
        if file_name == 'Persona.md':
            return self.persona_file(trader_name)
        if file_name in SHARED_FILE_NAMES:
            return self.shared_directory / file_name
        raise ValueError(f'Not one of the user files: {file_name!r}')

    def create_missing(self, trader_names: Sequence[str]) -> list[Path]:
        """Creates the folders, and writes each missing file from its template.

        Existing files are never overwritten. The intraday, scalper and positional traders get their own starter Persona.md; other traders get the general template. The starter subagents are written only when the agents folder does not exist yet, so one the user deleted stays deleted.

        Args:
            trader_names (Sequence[str]): The traders to prepare.

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
        for trader_name in trader_names:
            self.proposals_directory(trader_name).mkdir(
                parents=True, exist_ok=True
            )
            self.scratch_directory(trader_name).mkdir(
                parents=True, exist_ok=True
            )
            self.notes_directory(trader_name).mkdir(parents=True, exist_ok=True)
            for file_name in TRADER_FILE_NAMES:
                target = self.trader_directory(trader_name) / file_name
                template_name = file_name
                if file_name == 'Persona.md' and self._has_persona_template(
                    trader_name
                ):
                    template_name = f'personas/{trader_name}.md'
                if self._write_template_if_missing(target, template_name):
                    created.append(target)
        return created

    def _has_persona_template(self, trader_name: str) -> bool:
        """Says whether a starter trader has its own persona template.

        Args:
            trader_name (str): The trader's name, such as intraday.

        Returns:
            bool: True for the intraday, scalper and positional traders.
        """
        templates = (
            importlib.resources.files('trading_agent.workspace') / 'templates'
        )
        return (templates / 'personas' / f'{trader_name}.md').is_file()

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
        resource = templates
        for part in template_name.split('/'):
            resource = resource / part
        return resource.read_text(encoding='utf-8')

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
