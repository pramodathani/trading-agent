"""The skills one desk can use: the user's installed skills and the desk's own.

There are two homes, plus the skills of installed packages:

  workspace/shared/skills/installed/<name>/SKILL.md   imported by the user, read-only to every desk
  workspace/shared/packages/<package>/skills/<name>/  from packages, treated like installed skills
  workspace/desks/<desk>/skills/agent/<name>/SKILL.md  written by the desk itself

Only each skill's name and description go into the system prompt, as an index; load_skill reads a skill in full when the desk needs it. A skill whose required programs or environment variables are missing is hidden. When two skills share a name, the user's installed skill wins over a package's, and both win over the desk's own.

The library reads the folders afresh every time it is asked, so a newly imported or newly written skill shows up on the desk's next turn.

Typical usage example:

  library = SkillLibrary(installed_directory, agent_directory)
  index = library.index_text()
  skill = library.find('opening-range-breakout')
"""

import dataclasses
import logging
import os
import shutil
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from trading_agent.skills import skill as skill_module

_LOGGER = logging.getLogger(__name__)
INSTALLED = 'installed'
AGENT = 'agent'


@dataclasses.dataclass(frozen=True)
class HiddenSkill:
    """A skill that cannot be used here, and why.

    Attributes:
        skill: The skill.
        missing: The programs and environment variables it needs that are missing.
    """

    skill: skill_module.Skill
    missing: tuple[str, ...]


class SkillLibrary:
    """Finds and checks one desk's skills."""

    def __init__(
        self,
        installed_directory: Path,
        agent_directory: Path,
        program_finder: Callable[[str], str | None] = shutil.which,
        environment: Mapping[str, str] | None = None,
        package_skill_roots: Callable[[], Sequence[Path]] | None = None,
    ):
        """Creates the library without reading anything.

        Args:
            installed_directory (Path): The user's installed skills.
            agent_directory (Path): The desk's own skills.
            program_finder (Callable[[str], str | None]): Returns a program's path, or None when it is not installed; replaceable in tests.
            environment (Mapping[str, str] | None): The environment to check variables in; None uses os.environ.
            package_skill_roots (Callable[[], Sequence[Path]] | None): Returns the skills/ folders of installed packages, asked afresh each time, or None for no packages.
        """
        self.installed_directory = installed_directory
        self.agent_directory = agent_directory
        self._program_finder = program_finder
        self._environment = environment
        self._package_skill_roots = package_skill_roots
        self._parser = skill_module.SkillParser()

    def available(self) -> list[skill_module.Skill]:
        """The skills the desk can use, installed ones first, each sorted by name.

        Returns:
            list[skill_module.Skill]: The usable skills.
        """
        usable = []
        for skill in self._all():
            if not self._missing(skill):
                usable.append(skill)
        return usable

    def hidden(self) -> list[HiddenSkill]:
        """The skills hidden because something they need is missing.

        Returns:
            list[HiddenSkill]: The hidden skills and what each lacks.
        """
        hidden = []
        for skill in self._all():
            missing = self._missing(skill)
            if missing:
                hidden.append(HiddenSkill(skill=skill, missing=missing))
        return hidden

    def find(self, name: str) -> skill_module.Skill | None:
        """Finds a usable skill by name.

        Args:
            name (str): The skill's name.

        Returns:
            skill_module.Skill | None: The skill, or None when there is no usable skill of that name.
        """
        for skill in self.available():
            if skill.name == name:
                return skill
        return None

    def find_agent_skill(self, name: str) -> skill_module.Skill | None:
        """Finds one of the desk's own skills by name, usable or not.

        Args:
            name (str): The skill's name.

        Returns:
            skill_module.Skill | None: The skill, or None when the desk wrote no skill of that name.
        """
        for skill in self._read_folder(self.agent_directory, AGENT):
            if skill.name == name:
                return skill
        return None

    def is_installed_name(self, name: str) -> bool:
        """Says whether one of the user's installed skills has a name.

        Args:
            name (str): The name.

        Returns:
            bool: True when an installed skill has it.
        """
        for skill in self._installed_skills():
            if skill.name == name:
                return True
        return False

    def index_text(self) -> str:
        """The skills index for the system prompt.

        Returns:
            str: A titled section listing each usable skill's name and description, or saying there are none.
        """
        lines = [
            '===== Skills =====',
            'Skills are step-by-step procedures. When a task matches one, call load_skill with its name before you start, and follow it. Yours are marked "your own"; you can improve them with skill_patch.',
        ]
        skills = self.available()
        if not skills:
            lines.append('No skills are installed yet.')
        for skill in skills:
            marker = ''
            if skill.origin == AGENT:
                marker = ' (your own)'
            lines.append(f'- {skill.name}{marker}: {skill.description}')
        return '\n'.join(lines)

    def _all(self) -> list[skill_module.Skill]:
        """Every skill, with installed ones winning a name clash.

        Returns:
            list[skill_module.Skill]: The skills, installed first.
        """
        skills = self._installed_skills()
        installed_names = set()
        for skill in skills:
            installed_names.add(skill.name)
        for skill in self._read_folder(self.agent_directory, AGENT):
            if skill.name in installed_names:
                _LOGGER.warning(
                    'Desk skill %s is shadowed by an installed skill',
                    skill.name,
                )
                continue
            skills.append(skill)
        return skills

    def _installed_skills(self) -> list[skill_module.Skill]:
        """The user's installed skills, then those of packages, without repeated names.

        Returns:
            list[skill_module.Skill]: The skills; for a repeated name, the first found is kept.
        """
        folders = [
            self.installed_directory,
        ]
        if self._package_skill_roots is not None:
            folders.extend(self._package_skill_roots())
        skills = []
        names = set()
        for folder in folders:
            for skill in self._read_folder(folder, INSTALLED):
                if skill.name in names:
                    _LOGGER.warning(
                        'Skill %s in %s is shadowed by another of the same name',
                        skill.name,
                        folder,
                    )
                    continue
                names.add(skill.name)
                skills.append(skill)
        return skills

    def _read_folder(
        self,
        directory: Path,
        origin: str,
    ) -> list[skill_module.Skill]:
        """Reads every skill folder directly inside a folder.

        A folder whose SKILL.md is broken is logged and skipped, so one bad skill cannot hide the others. Folders whose names start with a dot, such as the archive, are skipped.

        Args:
            directory (Path): The folder.
            origin (str): "installed" or "agent".

        Returns:
            list[skill_module.Skill]: The skills, sorted by name.
        """
        if not directory.is_dir():
            return []
        skills = []
        for child in sorted(directory.iterdir()):
            if not child.is_dir() or child.name.startswith('.'):
                continue
            try:
                skills.append(self._parser.parse(child, origin))
            except skill_module.SkillFormatError as error:
                _LOGGER.warning('Skipped skill %s: %s', child, error)
        return skills

    def _missing(self, skill: skill_module.Skill) -> tuple[str, ...]:
        """Lists what a skill needs that is not here.

        Args:
            skill (skill_module.Skill): The skill.

        Returns:
            tuple[str, ...]: The missing programs and variables, empty when the skill can be used.
        """
        environment = self._environment
        if environment is None:
            environment = os.environ
        missing = []
        for program in skill.required_programs:
            if self._program_finder(program) is None:
                missing.append(f'program {program}')
        for variable in skill.required_environment:
            if not environment.get(variable):
                missing.append(f'environment variable {variable}')
        return tuple(missing)
