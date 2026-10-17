"""The skill_archive tool: takes one of the desk's own skills out of use without deleting it.

Typical usage example:

  tool = SkillArchiveTool(writer)
"""

import asyncio

import pydantic

from trading_agent.skills import skill_writer as skill_writer_module
from trading_agent.tools import tool


class SkillArchiveArguments(pydantic.BaseModel):
    """The arguments of skill_archive.

    Attributes:
        name: The skill to archive, which must be one of your own.
        reason: Why, for the skill ledger, such as "merged into gap-playbook".
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    name: str = pydantic.Field(min_length=1)
    reason: str = pydantic.Field(min_length=1)


class SkillArchiveTool(tool.Tool):
    """Archives one of the desk's own skills."""

    name = 'skill_archive'
    description = 'Takes one of your own skills out of the skills index by moving it to the archive, for example after merging it into another skill or when it proved wrong. Nothing is deleted, and the change can be undone.'
    arguments_model = SkillArchiveArguments

    def __init__(self, writer: skill_writer_module.SkillWriter):
        """Creates the tool.

        Args:
            writer (skill_writer_module.SkillWriter): Writes the desk's skills.
        """
        self._writer = writer

    async def run(self, arguments: SkillArchiveArguments) -> tool.ToolResult:
        """Archives the skill in a worker thread.

        Args:
            arguments (SkillArchiveArguments): The skill and the reason.

        Returns:
            tool.ToolResult: A confirmation, or why nothing changed.
        """
        try:
            await asyncio.to_thread(
                self._writer.archive,
                arguments.name,
                arguments.reason,
            )
        except skill_writer_module.SkillWriteError as error:
            return tool.ToolResult.error(str(error))
        return tool.ToolResult.success(f'Archived skill {arguments.name}.')
