"""The write_file tool: creates or replaces a file in the desk's own folders.

Typical usage example:

  tool = WriteFileTool(policy)
"""

import pydantic

from trading_agent.tools import path_policy as path_policy_module
from trading_agent.tools import tool


class WriteFileArguments(pydantic.BaseModel):
    """The arguments of write_file.

    Attributes:
        path: The file; a relative path starts at your desk folder.
        content: The complete text to write.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    path: str = pydantic.Field(min_length=1)
    content: str


class WriteFileTool(tool.Tool):
    """Writes a whole file."""

    name = 'write_file'
    description = 'Creates or replaces a text file with the complete content you give. You may write only inside memory/, notes/ and scratch/ of your desk folder, and your Memory.md.'
    arguments_model = WriteFileArguments

    def __init__(self, policy: path_policy_module.PathPolicy):
        """Creates the tool.

        Args:
            policy (path_policy_module.PathPolicy): The desk's read and write rules.
        """
        self._policy = policy

    async def run(self, arguments: WriteFileArguments) -> tool.ToolResult:
        """Writes the file, creating its folders when needed.

        Args:
            arguments (WriteFileArguments): The file and its content.

        Returns:
            tool.ToolResult: How much was written, or an error.
        """
        try:
            path = self._policy.writable(arguments.path)
        except path_policy_module.PathRefusedError as error:
            return tool.ToolResult.error(str(error))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(arguments.content, encoding='utf-8')
        line_count = len(arguments.content.splitlines())
        return tool.ToolResult.success(
            f'Wrote {line_count} lines to {path.relative_to(self._policy.desk_directory)}.'
        )
