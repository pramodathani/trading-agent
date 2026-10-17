"""Creates, patches and archives the skills a desk writes for itself.

Every change is snapshotted first, so it can be undone with `trading-agent checkpoints restore`, and recorded as one JSON line in the desk's skill ledger, `workspace/desks/<desk>/skills/ledger.jsonl`. The ledger sits outside skills/agent/, so restoring a checkpoint never erases the record of what happened. An archived skill moves to skills/agent/.archive/<name>/ and drops out of the index, but nothing is deleted.

Typical usage example:

  writer = SkillWriter(library, checkpoints, ledger_file)
  writer.create('gap-down-playbook', 'What to do when NIFTY gaps down.', body, [], [], 'learned on 19 Oct')
"""

import datetime
import json
import logging
import shutil
from pathlib import Path

from trading_agent.memory import checkpoints as checkpoints_module
from trading_agent.skills import skill as skill_module
from trading_agent.skills import skill_library as skill_library_module

_LOGGER = logging.getLogger(__name__)
ARCHIVE_FOLDER_NAME = '.archive'


class SkillWriteError(ValueError):
    """A skill change was refused, with a reason the desk can act on."""


class SkillWriter:
    """Changes one desk's own skills."""

    def __init__(
        self,
        library: skill_library_module.SkillLibrary,
        checkpoints: checkpoints_module.Checkpoints | None,
        ledger_file: Path,
    ):
        """Creates the writer.

        Args:
            library (skill_library_module.SkillLibrary): The desk's skills, for name checks.
            checkpoints (checkpoints_module.Checkpoints | None): Snapshots the desk's files before each change, or None to take none.
            ledger_file (Path): The JSON-lines record of every change.
        """
        self._library = library
        self._checkpoints = checkpoints
        self._ledger_file = ledger_file
        self._parser = skill_module.SkillParser()

    def create(
        self,
        name: str,
        description: str,
        body: str,
        required_programs: list[str],
        required_environment: list[str],
        reason: str,
    ) -> Path:
        """Writes a new skill.

        Args:
            name (str): The skill's name.
            description (str): When to use it.
            body (str): The Markdown instructions.
            required_programs (list[str]): Programs it needs.
            required_environment (list[str]): Environment variables it needs.
            reason (str): Why it was written, for the ledger.

        Returns:
            Path: The new SKILL.md.

        Raises:
            SkillWriteError: The name or description is not valid, or a skill of that name exists.
        """
        try:
            self._parser.check_name(name)
            self._parser.check_description(description)
        except skill_module.SkillFormatError as error:
            raise SkillWriteError(str(error)) from error
        if self._library.is_installed_name(name):
            raise SkillWriteError(
                f"{name} is one of the user's installed skills; choose another name."
            )
        directory = self._library.agent_directory / name
        if directory.exists():
            raise SkillWriteError(
                f'You already have a skill named {name}; change it with skill_patch.'
            )
        self._snapshot(f'before skill_create {name}')
        text = self._parser.frontmatter_text(
            name,
            description,
            required_programs,
            required_environment,
        )
        directory.mkdir(parents=True)
        path = directory / skill_module.SKILL_FILE_NAME
        path.write_text(text + '\n' + body.strip() + '\n', encoding='utf-8')
        self._record('create', name, reason)
        return path

    def patch(
        self,
        name: str,
        old_text: str,
        new_text: str,
        reason: str,
    ) -> int:
        """Replaces exact text in one of the desk's skills, frontmatter included.

        Args:
            name (str): The skill's name.
            old_text (str): The text to replace, which must appear exactly once.
            new_text (str): The replacement.
            reason (str): Why, for the ledger.

        Returns:
            int: The skill file's new length in characters.

        Raises:
            SkillWriteError: The skill is not the desk's own, old_text is missing or repeated, or the result is not a valid skill.
        """
        skill = self._own_skill(name)
        path = skill.directory / skill_module.SKILL_FILE_NAME
        text = path.read_text(encoding='utf-8')
        occurrences = text.count(old_text)
        if occurrences == 0:
            raise SkillWriteError(
                'old_text was not found. Load the skill again and copy the text exactly.'
            )
        if occurrences > 1:
            raise SkillWriteError(
                f'old_text appears {occurrences} times; include more surrounding text.'
            )
        new_skill_text = text.replace(old_text, new_text)
        self._check_still_valid(skill, new_skill_text)
        self._snapshot(f'before skill_patch {name}')
        path.write_text(new_skill_text, encoding='utf-8')
        self._record('patch', name, reason)
        return len(new_skill_text)

    def archive(self, name: str, reason: str) -> Path:
        """Moves one of the desk's skills out of use, into the archive.

        Args:
            name (str): The skill's name.
            reason (str): Why, for the ledger.

        Returns:
            Path: Where the skill now lives.

        Raises:
            SkillWriteError: The skill is not the desk's own.
        """
        skill = self._own_skill(name)
        self._snapshot(f'before skill_archive {name}')
        archive = self._library.agent_directory / ARCHIVE_FOLDER_NAME
        archive.mkdir(parents=True, exist_ok=True)
        target = archive / name
        if target.exists():
            stamp = datetime.datetime.now(datetime.UTC).strftime('%Y%m%d%H%M%S')
            target = archive / f'{name}-{stamp}'
        shutil.move(str(skill.directory), str(target))
        self._record('archive', name, reason)
        return target

    def _own_skill(self, name: str) -> skill_module.Skill:
        """Finds one of the desk's own skills.

        Args:
            name (str): The skill's name.

        Returns:
            skill_module.Skill: The skill.

        Raises:
            SkillWriteError: The desk has no such skill, for example because it is an installed one.
        """
        skill = self._library.find_agent_skill(name)
        if skill is not None:
            return skill
        if self._library.is_installed_name(name):
            raise SkillWriteError(
                f"{name} is one of the user's installed skills, which you cannot change. Write your own variant with skill_create."
            )
        raise SkillWriteError(f'You have no skill named {name}.')

    def _check_still_valid(
        self,
        skill: skill_module.Skill,
        new_skill_text: str,
    ) -> None:
        """Checks that a patched SKILL.md still parses and keeps its name.

        Args:
            skill (skill_module.Skill): The skill before the patch.
            new_skill_text (str): The patched text.

        Raises:
            SkillWriteError: The patched text is not a valid skill, or renames it.
        """
        trial_directory = (
            self._library.agent_directory / '.patch-check' / skill.name
        )
        trial_directory.mkdir(parents=True, exist_ok=True)
        trial_path = trial_directory / skill_module.SKILL_FILE_NAME
        try:
            trial_path.write_text(new_skill_text, encoding='utf-8')
            patched = self._parser.parse(trial_directory, skill.origin)
        except skill_module.SkillFormatError as error:
            raise SkillWriteError(
                f'The patch would break the skill: {error}'
            ) from error
        finally:
            shutil.rmtree(trial_directory.parent, ignore_errors=True)
        if patched.name != skill.name:
            raise SkillWriteError(
                'A patch cannot rename a skill; create a new one and archive this one.'
            )

    def _snapshot(self, reason: str) -> None:
        """Snapshots the desk's files, logging rather than failing when git does.

        Args:
            reason (str): What is about to happen.
        """
        if self._checkpoints is None:
            return
        try:
            self._checkpoints.snapshot(reason)
        except checkpoints_module.CheckpointError:
            _LOGGER.exception('Could not snapshot %s', reason)

    def _record(self, action: str, name: str, reason: str) -> None:
        """Appends one change to the ledger.

        Args:
            action (str): "create", "patch" or "archive".
            name (str): The skill.
            reason (str): Why.
        """
        self._ledger_file.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            {
                'at': datetime.datetime.now(datetime.UTC).isoformat(),
                'action': action,
                'skill': name,
                'reason': reason,
            },
            ensure_ascii=False,
        )
        with self._ledger_file.open('a', encoding='utf-8') as ledger:
            ledger.write(line + '\n')
