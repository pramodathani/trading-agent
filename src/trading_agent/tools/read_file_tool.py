"""The read_file tool: shows a text file with line numbers.

Typical usage example:

  tool = ReadFileTool(policy)
"""

import pydantic

from trading_agent.tools import path_policy as path_policy_module
from trading_agent.tools import tool


class ReadFileArguments(pydantic.BaseModel):
    """The arguments of read_file.

    Attributes:
        path: The file; a relative path starts at your trader folder.
        start_line: The first line to show, counting from 1.
        maximum_lines: How many lines to show at most.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    path: str = pydantic.Field(min_length=1)
    start_line: int = pydantic.Field(default=1, ge=1)
    maximum_lines: int = pydantic.Field(default=400, ge=1, le=2000)


class ReadFileTool(tool.Tool):
    """Reads part of a text file."""

    name = 'read_file'
    description = 'Shows a text file with line numbers. A relative path starts at your trader folder (for example Memory.md or notes/2026-10-19.md). Files that hold secrets cannot be read.'
    arguments_model = ReadFileArguments

    def __init__(self, policy: path_policy_module.PathPolicy):
        """Creates the tool.

        Args:
            policy (path_policy_module.PathPolicy): The trader's read and write rules.
        """
        self._policy = policy

    async def run(self, arguments: ReadFileArguments) -> tool.ToolResult:
        """Reads the requested lines.

        Args:
            arguments (ReadFileArguments): The file and which lines.

        Returns:
            tool.ToolResult: The numbered lines, with a note when more follow, or an error.
        """
        try:
            path = self._policy.readable(arguments.path)
        except path_policy_module.PathRefusedError as error:
            return tool.ToolResult.error(str(error))
        if not path.is_file():
            return tool.ToolResult.error(f'{arguments.path} is not a file.')
        lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
        first = arguments.start_line - 1
        shown = lines[first : first + arguments.maximum_lines]
        numbered = []
        for offset, line in enumerate(shown):
            numbered.append(f'{first + offset + 1:6}  {line}')
        remaining = len(lines) - first - len(shown)
        if remaining > 0:
            numbered.append(
                f'[{remaining} more lines; read again with start_line={first + len(shown) + 1}]'
            )
        if not numbered:
            numbered.append(f'[{arguments.path} has {len(lines)} lines]')
        return tool.ToolResult.success('\n'.join(numbered))
