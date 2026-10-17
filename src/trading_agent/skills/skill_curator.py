"""Keeps a desk's own skills tidy, once a day when its session rolls over.

The curator has two halves:

- In code, `archive_unused` archives the desk's skills that have not been used for a number of days (30 by default). A skill never used counts from the day its file was last changed.
- For the model, `review_request` writes the text of a review turn: each of the desk's skills with its use counts, and instructions to patch skills that keep running into trouble, merge duplicates, and turn any procedure worth repeating from the day into a new skill. The session keeper runs that turn right after the day's summary, while the whole day is still in the desk's context.

Installed skills are never touched; they belong to the user.

Typical usage example:

  curator = SkillCurator(library, usage_reader, writer, 30)
  archived = curator.archive_unused(datetime.date(2026, 10, 19))
  text = curator.review_request(datetime.date(2026, 10, 19))
"""

import datetime
import logging

from trading_agent.skills import skill as skill_module
from trading_agent.skills import skill_library as skill_library_module
from trading_agent.skills import skill_usage as skill_usage_module
from trading_agent.skills import skill_writer as skill_writer_module

_LOGGER = logging.getLogger(__name__)


class SkillCurator:
    """Reviews one desk's own skills."""

    def __init__(
        self,
        library: skill_library_module.SkillLibrary,
        usage_reader: skill_usage_module.SkillUsageReader,
        writer: skill_writer_module.SkillWriter,
        archive_after_days: int,
    ):
        """Creates the curator.

        Args:
            library (skill_library_module.SkillLibrary): The desk's skills.
            usage_reader (skill_usage_module.SkillUsageReader): The desk's usage statistics.
            writer (skill_writer_module.SkillWriter): Archives skills.
            archive_after_days (int): How many days without use before a skill is archived.
        """
        self._library = library
        self._usage_reader = usage_reader
        self._writer = writer
        self._archive_after_days = archive_after_days

    def archive_unused(self, today: datetime.date) -> list[str]:
        """Archives the desk's skills unused for too long.

        Args:
            today (datetime.date): Today's India date.

        Returns:
            list[str]: The names of the skills archived.
        """
        statistics = self._usage_reader.statistics()
        archived = []
        for skill in self._own_skills():
            last_day = self._last_active_day(skill, statistics)
            idle_days = (today - last_day).days
            if idle_days < self._archive_after_days:
                continue
            try:
                self._writer.archive(
                    skill.name,
                    f'not used for {idle_days} days',
                )
            except skill_writer_module.SkillWriteError:
                _LOGGER.exception('Could not archive skill %s', skill.name)
                continue
            archived.append(skill.name)
        return archived

    def review_request(
        self,
        trading_date: datetime.date,
        archived: list[str],
    ) -> str:
        """Writes the text of the daily skill review turn.

        Args:
            trading_date (datetime.date): The day being closed.
            archived (list[str]): Skills archived just before, so the desk knows.

        Returns:
            str: The request.
        """
        statistics = self._usage_reader.statistics()
        lines = [
            f'[Skill review for {trading_date.isoformat()}. Your summary is saved; this turn is about your skills.]',
        ]
        own_skills = self._own_skills()
        if own_skills:
            lines.append('Your own skills, with how they have been used:')
            for skill in own_skills:
                lines.append(
                    f'- {skill.name}: {self._usage_text(statistics.get(skill.name))}. {skill.description}'
                )
        else:
            lines.append('You have no skills of your own yet.')
        if archived:
            lines.append(
                f'Archived just now for not being used in {self._archive_after_days} days: {", ".join(archived)}.'
            )
        lines.extend(
            [
                'Do what is useful, and nothing more:',
                '1. A skill with troubled uses may have a wrong or missing step: load it, and fix it with skill_patch if today shows what was wrong.',
                '2. Two skills that do the same job should become one: write the merged skill with skill_create, then archive the others with skill_archive.',
                '3. If you worked out a procedure today that you will need again, such as a multi-step analysis or an order routine, write it down with skill_create.',
                'Then reply with one line saying what you changed, or "No skill changes".',
            ]
        )
        return '\n'.join(lines)

    def _own_skills(self) -> list[skill_module.Skill]:
        """The desk's own skills, usable or not.

        Returns:
            list[skill_module.Skill]: The skills.
        """
        skills = []
        for skill in self._library.available():
            if skill.origin == skill_library_module.AGENT:
                skills.append(skill)
        for hidden in self._library.hidden():
            if hidden.skill.origin == skill_library_module.AGENT:
                skills.append(hidden.skill)
        return skills

    def _last_active_day(
        self,
        skill: skill_module.Skill,
        statistics: dict[str, skill_usage_module.SkillStatistics],
    ) -> datetime.date:
        """The last day a skill was used, or changed when it was never used.

        Args:
            skill (skill_module.Skill): The skill.
            statistics (dict[str, skill_usage_module.SkillStatistics]): The usage statistics.

        Returns:
            datetime.date: The day.
        """
        used = statistics.get(skill.name)
        if used is not None and used.last_used:
            return datetime.date.fromisoformat(used.last_used[:10])
        changed = (
            (skill.directory / skill_module.SKILL_FILE_NAME).stat().st_mtime
        )
        return datetime.datetime.fromtimestamp(changed, datetime.UTC).date()

    def _usage_text(
        self,
        statistics: skill_usage_module.SkillStatistics | None,
    ) -> str:
        """Describes a skill's use in words.

        Args:
            statistics (skill_usage_module.SkillStatistics | None): Its statistics, or None when never used.

        Returns:
            str: Such as "used 4 times, 1 troubled, last on 2026-10-19".
        """
        if statistics is None:
            return 'never used'
        return f'used {statistics.uses} times, {statistics.troubled_uses} troubled, last on {statistics.last_used[:10]}'
