"""The subagents every desk can delegate to.

Definitions are Markdown files in workspace/shared/agents/, which belongs to the user, and in the agents/ folder of each installed package. When two files define the same name, the user's own folder wins. The folders are read afresh every time, so a new definition is available on the desk's next turn.

Typical usage example:

  library = SubagentLibrary(Path('workspace/shared/agents'), packages.agent_roots)
  definition = library.find('news_reader')
"""

import dataclasses
import logging
from collections.abc import Callable, Sequence
from pathlib import Path

from trading_agent.subagents import subagent_definition as definition_module

_LOGGER = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class BrokenDefinition:
    """A subagent file that could not be read, and why.

    Attributes:
        path: The file.
        error: The reason.
    """

    path: Path
    error: str


class SubagentLibrary:
    """Finds subagent definitions."""

    def __init__(
        self,
        agents_directory: Path,
        package_agent_roots: Callable[[], Sequence[Path]] | None = None,
    ):
        """Describes the folders without reading them.

        Args:
            agents_directory (Path): workspace/shared/agents.
            package_agent_roots (Callable[[], Sequence[Path]] | None): Returns the agents/ folders of installed packages, or None for no packages.
        """
        self.agents_directory = agents_directory
        self._package_agent_roots = package_agent_roots
        self._parser = definition_module.SubagentParser()

    def definitions(self) -> list[definition_module.SubagentDefinition]:
        """Every readable definition, the user's first, without repeated names.

        Returns:
            list[definition_module.SubagentDefinition]: The subagents.
        """
        definitions, _ = self._read_all()
        return definitions

    def broken(self) -> list[BrokenDefinition]:
        """The files that could not be read.

        Returns:
            list[BrokenDefinition]: Each broken file and why.
        """
        _, broken = self._read_all()
        return broken

    def find(self, name: str) -> definition_module.SubagentDefinition | None:
        """Finds one subagent by name.

        Args:
            name (str): The name.

        Returns:
            definition_module.SubagentDefinition | None: The subagent, or None when there is none of that name.
        """
        for definition in self.definitions():
            if definition.name == name:
                return definition
        return None

    def index_text(self) -> str:
        """The section of the desk's prompt listing its subagents.

        Returns:
            str: The section, or an empty string when there are no subagents.
        """
        definitions = self.definitions()
        if not definitions:
            return ''
        lines = [
            '===== Subagents =====',
            'Subagents are helpers you can hand a self-contained task to with delegate_task. Up to four tasks run at the same time, each with its own fresh conversation, so give each one everything it needs in the task text. They report back to you; they cannot talk to the user or start subagents of their own.',
        ]
        for definition in definitions:
            lines.append(f'- {definition.name}: {definition.description}')
        return '\n'.join(lines)

    def _read_all(
        self,
    ) -> tuple[
        list[definition_module.SubagentDefinition], list[BrokenDefinition]
    ]:
        """Reads every folder.

        Returns:
            tuple[list[definition_module.SubagentDefinition], list[BrokenDefinition]]: A tuple (definitions, broken), where definitions are the readable subagents without repeated names and broken the files that failed.
        """
        folders = [
            self.agents_directory,
        ]
        if self._package_agent_roots is not None:
            folders.extend(self._package_agent_roots())
        definitions = []
        broken = []
        names = set()
        for folder in folders:
            if not folder.is_dir():
                continue
            for path in sorted(folder.glob('*.md')):
                try:
                    definition = self._parser.parse(path)
                except definition_module.SubagentFormatError as error:
                    broken.append(BrokenDefinition(path=path, error=str(error)))
                    continue
                if definition.name in names:
                    _LOGGER.warning(
                        'Subagent %s in %s is shadowed by another of the same name',
                        definition.name,
                        path,
                    )
                    continue
                names.add(definition.name)
                definitions.append(definition)
        return definitions, broken
