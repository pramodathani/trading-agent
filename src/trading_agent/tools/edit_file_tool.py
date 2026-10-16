"""The edit_file tool: replaces exact text in a file in the desk's own folders.

Typical usage example:

  tool = EditFileTool(policy)
"""

import pydantic

from trading_agent.tools import path_policy as path_policy_module
from trading_agent.tools import tool


class EditFileArguments(pydantic.BaseModel):
    """The arguments of edit_file.

    Attributes:
        path: The file; a relative path starts at your desk folder.
        old_text: The exact text to replace, copied from the file.
        new_text: The text to put in its place.
        replace_all: Whether to replace every occurrence instead of exactly one.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    path: str = pydantic.Field(min_length=1)
    old_text: str = pydantic.Field(min_length=1)
    new_text: str
    replace_all: bool = False


class EditFileTool(tool.Tool):
    """Replaces exact text in a file."""

    name = 'edit_file'
    description = 'Replaces exact text in one of your files. old_text must appear exactly once, unless replace_all is true. You may edit only inside memory/, notes/ and scratch/ of your desk folder, and your Memory.md.'
    arguments_model = EditFileArguments

    def __init__(self, policy: path_policy_module.PathPolicy):
        """Creates the tool.

        Args:
            policy (path_policy_module.PathPolicy): The desk's read and write rules.
        """
        self._policy = policy

    async def run(self, arguments: EditFileArguments) -> tool.ToolResult:
        """Makes the replacement.

        Args:
            arguments (EditFileArguments): The file, the text to find and its replacement.

        Returns:
            tool.ToolResult: How many places changed, or an error saying why nothing did.
        """
        try:
            path = self._policy.writable(arguments.path)
        except path_policy_module.PathRefusedError as error:
            return tool.ToolResult.error(str(error))
        if not path.is_file():
            return tool.ToolResult.error(
                f'{arguments.path} does not exist; create it with write_file.'
            )
        text = path.read_text(encoding='utf-8')
        occurrences = text.count(arguments.old_text)
        if occurrences == 0:
            return tool.ToolResult.error(
                'old_text was not found. Read the file again and copy the text exactly.'
            )
        if occurrences > 1 and not arguments.replace_all:
            return tool.ToolResult.error(
                f'old_text appears {occurrences} times. Include more surrounding text so it appears once, or set replace_all to true.'
            )
        path.write_text(
            text.replace(arguments.old_text, arguments.new_text),
            encoding='utf-8',
        )
        return tool.ToolResult.success(
            f'Replaced {occurrences} occurrence(s) in {path.relative_to(self._policy.desk_directory)}.'
        )
