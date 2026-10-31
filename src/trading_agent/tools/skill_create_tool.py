"""The skill_create tool: writes down a procedure as one of the trader's own skills.

Typical usage example:

  tool = SkillCreateTool(writer)
"""

import asyncio

import pydantic

from trading_agent.skills import skill_writer as skill_writer_module
from trading_agent.tools import tool


class SkillCreateArguments(pydantic.BaseModel):
    """The arguments of skill_create.

    Attributes:
        name: The new skill's name: lower-case letters, digits and hyphens.
        description: One or two sentences saying when to use it; this is what the skills index shows.
        instructions: The procedure in Markdown, as numbered steps with the tools to use and what to check.
        required_programs: Programs the skill needs, such as python3.
        required_environment: Environment variables the skill needs.
        reason: Why the skill is worth keeping, for the skill ledger.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    name: str = pydantic.Field(min_length=1, max_length=64)
    description: str = pydantic.Field(min_length=1, max_length=1024)
    instructions: str = pydantic.Field(min_length=1)
    required_programs: list[str] = []
    required_environment: list[str] = []
    reason: str = pydantic.Field(min_length=1)


class SkillCreateTool(tool.Tool):
    """Creates one of the trader's own skills."""

    name = 'skill_create'
    description = "Writes a procedure you worked out as one of your own skills, so you can follow it again with load_skill. Use it after a multi-step task you will need again, such as an analysis routine or an order routine. Write the instructions as numbered steps that name the tools to use and what to check, with no facts that will go stale, such as today's prices. The change is snapshotted, so it can be undone."
    arguments_model = SkillCreateArguments

    def __init__(self, writer: skill_writer_module.SkillWriter):
        """Creates the tool.

        Args:
            writer (skill_writer_module.SkillWriter): Writes the trader's skills.
        """
        self._writer = writer

    async def run(self, arguments: SkillCreateArguments) -> tool.ToolResult:
        """Writes the skill in a worker thread, because the snapshot runs git.

        Args:
            arguments (SkillCreateArguments): The skill.

        Returns:
            tool.ToolResult: Where the skill was written, or why it was refused.
        """
        try:
            await asyncio.to_thread(
                self._writer.create,
                arguments.name,
                arguments.description,
                arguments.instructions,
                arguments.required_programs,
                arguments.required_environment,
                arguments.reason,
            )
        except skill_writer_module.SkillWriteError as error:
            return tool.ToolResult.error(str(error))
        return tool.ToolResult.success(
            f'Created skill {arguments.name}. It is in the skills index from your next turn.'
        )
