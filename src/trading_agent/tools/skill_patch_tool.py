"""The skill_patch tool: corrects one of the desk's own skills.

Typical usage example:

  tool = SkillPatchTool(writer)
"""

import asyncio

import pydantic

from trading_agent.skills import skill_writer as skill_writer_module
from trading_agent.tools import tool


class SkillPatchArguments(pydantic.BaseModel):
    """The arguments of skill_patch.

    Attributes:
        name: The skill to change, which must be one of your own.
        old_text: The exact text to replace, copied from the skill; it must appear once.
        new_text: The replacement.
        reason: What was wrong, for the skill ledger.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    name: str = pydantic.Field(min_length=1)
    old_text: str = pydantic.Field(min_length=1)
    new_text: str
    reason: str = pydantic.Field(min_length=1)


class SkillPatchTool(tool.Tool):
    """Replaces text in one of the desk's own skills."""

    name = 'skill_patch'
    description = "Fixes one of your own skills by replacing exact text in its SKILL.md, the description at the top included. Use it when following the skill went wrong because a step was wrong or missing. old_text must appear exactly once; load the skill first to copy it. The user's installed skills cannot be changed. The change is snapshotted, so it can be undone."
    arguments_model = SkillPatchArguments

    def __init__(self, writer: skill_writer_module.SkillWriter):
        """Creates the tool.

        Args:
            writer (skill_writer_module.SkillWriter): Writes the desk's skills.
        """
        self._writer = writer

    async def run(self, arguments: SkillPatchArguments) -> tool.ToolResult:
        """Makes the replacement in a worker thread.

        Args:
            arguments (SkillPatchArguments): The skill and the replacement.

        Returns:
            tool.ToolResult: A confirmation, or why nothing changed.
        """
        try:
            await asyncio.to_thread(
                self._writer.patch,
                arguments.name,
                arguments.old_text,
                arguments.new_text,
                arguments.reason,
            )
        except skill_writer_module.SkillWriteError as error:
            return tool.ToolResult.error(str(error))
        return tool.ToolResult.success(f'Patched skill {arguments.name}.')
