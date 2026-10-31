"""One skill: a folder holding a SKILL.md file and, optionally, scripts/ and references/.

SKILL.md follows the open Agent Skills format that Claude Code and Hermes use: YAML frontmatter between two `---` lines, then Markdown instructions.

  ---
  name: opening-range-breakout
  description: How to trade the first 15-minute range of an NSE stock.
  requires:
    programs: [python3]
    environment: [SOME_API_KEY]
  ---
  # Opening range breakout
  ...

A skill can say what it needs with `requires` (programs and environment variables), or with Hermes's `prerequisites` (commands and env_vars). A skill whose needs are missing is hidden from the trader.

Typical usage example:

  skill = SkillParser().parse(Path('workspace/shared/skills/installed/opening-range-breakout'), 'installed')
"""

import dataclasses
import re
from pathlib import Path
from typing import Any

import yaml

SKILL_FILE_NAME = 'SKILL.md'
NAME_PATTERN = re.compile(r'^[a-z0-9][a-z0-9-]{0,63}$')
MAXIMUM_DESCRIPTION_CHARACTERS = 1024
_FRONTMATTER_PATTERN = re.compile(
    r'\A---\s*\n(.*?)\n---\s*(?:\n|\Z)', re.DOTALL
)


class SkillFormatError(ValueError):
    """A SKILL.md file is missing, or its frontmatter is not valid."""


@dataclasses.dataclass(frozen=True)
class Skill:
    """One parsed skill.

    Attributes:
        name: The skill's name, lower-case letters, digits and hyphens.
        description: One or two sentences saying when to use it, shown in the skills index.
        body: The Markdown instructions after the frontmatter.
        directory: The skill's folder.
        origin: "installed" for the user's skills, "agent" for skills the trader wrote.
        required_programs: Programs that must be on the PATH.
        required_environment: Environment variables that must be set.
    """

    name: str
    description: str
    body: str
    directory: Path
    origin: str
    required_programs: tuple[str, ...]
    required_environment: tuple[str, ...]

    def bundled_files(self) -> list[Path]:
        """The files in the skill's scripts/ and references/ folders.

        Returns:
            list[Path]: The files, sorted by path.
        """
        files = []
        for folder_name in ('scripts', 'references'):
            folder = self.directory / folder_name
            if not folder.is_dir():
                continue
            for path in sorted(folder.rglob('*')):
                if path.is_file():
                    files.append(path)
        return files


class SkillParser:
    """Reads SKILL.md files."""

    def parse(self, directory: Path, origin: str) -> Skill:
        """Reads the skill in a folder.

        Args:
            directory (Path): The skill's folder.
            origin (str): "installed" or "agent".

        Returns:
            Skill: The skill.

        Raises:
            SkillFormatError: SKILL.md is missing, has no frontmatter, or its name or description is not valid.
        """
        path = directory / SKILL_FILE_NAME
        if not path.is_file():
            raise SkillFormatError(f'{directory} has no {SKILL_FILE_NAME}')
        text = path.read_text(encoding='utf-8')
        match = _FRONTMATTER_PATTERN.match(text)
        if match is None:
            raise SkillFormatError(
                f'{path} does not start with frontmatter between two --- lines'
            )
        try:
            frontmatter = yaml.safe_load(match.group(1))
        except yaml.YAMLError as error:
            raise SkillFormatError(
                f'{path} has frontmatter that is not valid YAML: {error}'
            ) from error
        if not isinstance(frontmatter, dict):
            raise SkillFormatError(f'{path} frontmatter is not a mapping')
        name = str(frontmatter.get('name', '')).strip()
        description = str(frontmatter.get('description', '')).strip()
        self.check_name(name)
        self.check_description(description)
        programs, environment = self._requirements(frontmatter)
        return Skill(
            name=name,
            description=description,
            body=text[match.end() :].strip(),
            directory=directory,
            origin=origin,
            required_programs=programs,
            required_environment=environment,
        )

    def check_name(self, name: str) -> None:
        """Checks a skill name.

        Args:
            name (str): The name.

        Raises:
            SkillFormatError: The name is not 1 to 64 lower-case letters, digits and hyphens starting with a letter or digit.
        """
        if not NAME_PATTERN.match(name):
            raise SkillFormatError(
                f'Skill name {name!r} must be 1 to 64 lower-case letters, digits and hyphens, starting with a letter or digit'
            )

    def check_description(self, description: str) -> None:
        """Checks a skill description.

        Args:
            description (str): The description.

        Raises:
            SkillFormatError: The description is empty or longer than 1,024 characters.
        """
        if not description:
            raise SkillFormatError('A skill needs a description')
        if len(description) > MAXIMUM_DESCRIPTION_CHARACTERS:
            raise SkillFormatError(
                'A skill description must be at most 1,024 characters'
            )

    def frontmatter_text(
        self,
        name: str,
        description: str,
        required_programs: list[str],
        required_environment: list[str],
    ) -> str:
        """Writes the frontmatter for a new skill.

        Args:
            name (str): The skill's name.
            description (str): Its description.
            required_programs (list[str]): Programs it needs.
            required_environment (list[str]): Environment variables it needs.

        Returns:
            str: The frontmatter, including both --- lines.
        """
        data: dict[str, Any] = {
            'name': name,
            'description': description,
        }
        requires = {}
        if required_programs:
            requires['programs'] = list(required_programs)
        if required_environment:
            requires['environment'] = list(required_environment)
        if requires:
            data['requires'] = requires
        dumped = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
        return f'---\n{dumped}---\n'

    def _requirements(
        self,
        frontmatter: dict[str, Any],
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Reads what a skill needs, from `requires` or Hermes's `prerequisites`.

        Args:
            frontmatter (dict[str, Any]): The parsed frontmatter.

        Returns:
            tuple[tuple[str, ...], tuple[str, ...]]: A tuple (programs, environment), where programs are the programs and environment the variables it needs.
        """
        programs = []
        environment = []
        requires = frontmatter.get('requires')
        if isinstance(requires, dict):
            programs.extend(self._strings(requires.get('programs')))
            environment.extend(self._strings(requires.get('environment')))
        prerequisites = frontmatter.get('prerequisites')
        if isinstance(prerequisites, dict):
            programs.extend(self._strings(prerequisites.get('commands')))
            environment.extend(self._strings(prerequisites.get('env_vars')))
        return tuple(programs), tuple(environment)

    def _strings(self, value: Any) -> list[str]:
        """Turns a YAML value into a list of strings.

        Args:
            value (Any): A list, a single string, or None.

        Returns:
            list[str]: The strings.
        """
        if value is None:
            return []
        if isinstance(value, str):
            return [
                value,
            ]
        if isinstance(value, list):
            return [str(item) for item in value]
        return []
