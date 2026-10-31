"""The write_file tool: creates or replaces a file in the trader's own folders.

Typical usage example:

  tool = WriteFileTool(policy, checkpoints)
"""

import asyncio
import logging
from pathlib import Path

import pydantic

from trading_agent.memory import checkpoints as checkpoints_module
from trading_agent.tools import path_policy as path_policy_module
from trading_agent.tools import tool

_LOGGER = logging.getLogger(__name__)


class WriteFileArguments(pydantic.BaseModel):
    """The arguments of write_file.

    Attributes:
        path: The file; a relative path starts at your trader folder.
        content: The complete text to write.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    path: str = pydantic.Field(min_length=1)
    content: str


class WriteFileTool(tool.Tool):
    """Writes a whole file."""

    name = 'write_file'
    description = 'Creates or replaces a text file with the complete content you give. You may write only inside memory/, notes/ and scratch/ of your trader folder, and your Memory.md.'
    arguments_model = WriteFileArguments

    def __init__(
        self,
        policy: path_policy_module.PathPolicy,
        checkpoints: checkpoints_module.Checkpoints | None = None,
    ):
        """Creates the tool.

        Args:
            policy (path_policy_module.PathPolicy): The trader's read and write rules.
            checkpoints (checkpoints_module.Checkpoints | None): Snapshots the trader's files before each change, or None to take none.
        """
        self._policy = policy
        self._checkpoints = checkpoints

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
        await self._snapshot(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(arguments.content, encoding='utf-8')
        line_count = len(arguments.content.splitlines())
        return tool.ToolResult.success(
            f'Wrote {line_count} lines to {path.relative_to(self._policy.trader_directory)}.'
        )

    async def _snapshot(self, path: Path) -> None:
        """Snapshots the trader's files before the change, so it can be undone.

        A failed snapshot is logged and does not stop the change, because the trader must keep working.

        Args:
            path (Path): The file about to change.
        """
        if self._checkpoints is None:
            return
        relative_path = path.relative_to(self._policy.trader_directory)
        try:
            await asyncio.to_thread(
                self._checkpoints.snapshot,
                f'before {self.name} {relative_path}',
            )
        except checkpoints_module.CheckpointError:
            _LOGGER.exception('Could not snapshot before %s', self.name)
