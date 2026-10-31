"""The view_image tool: shows the model a picture file, such as a chart it made or one the user sent earlier.

Typical usage example:

  tool = ViewImageTool(policy)
"""

import asyncio
from pathlib import Path

import pydantic

from trading_agent.attachments import image_preparer as image_preparer_module
from trading_agent.tools import path_policy as path_policy_module
from trading_agent.tools import tool


class ViewImageArguments(pydantic.BaseModel):
    """The arguments of view_image.

    Attributes:
        path: The picture; a relative path starts at your trader folder.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    path: str = pydantic.Field(min_length=1)


class ViewImageTool(tool.Tool):
    """Shows the model a PNG, JPEG, WebP or GIF file."""

    name = 'view_image'
    description = 'Looks at a picture file (PNG, JPEG, WebP or GIF) and shows it to you, for example a chart you drew in scratch/, a screenshot you took earlier, or a picture the user sent in an earlier message. A relative path starts at your trader folder. Models that cannot see pictures get nothing useful from it.'
    arguments_model = ViewImageArguments

    def __init__(
        self,
        policy: path_policy_module.PathPolicy,
        image_preparer: image_preparer_module.ImagePreparer | None = None,
    ):
        """Creates the tool.

        Args:
            policy (path_policy_module.PathPolicy): The trader's read rules.
            image_preparer (image_preparer_module.ImagePreparer | None): Checks and resizes pictures; None for a new one.
        """
        self._policy = policy
        self._image_preparer = (
            image_preparer or image_preparer_module.ImagePreparer()
        )

    async def run(self, arguments: ViewImageArguments) -> tool.ToolResult:
        """Loads the picture.

        Args:
            arguments (ViewImageArguments): The picture's path.

        Returns:
            tool.ToolResult: A line naming the picture, with the picture attached, or an error.
        """
        try:
            path = self._policy.readable(arguments.path)
        except path_policy_module.PathRefusedError as error:
            return tool.ToolResult.error(str(error))
        if not path.is_file():
            return tool.ToolResult.error(f'{arguments.path} is not a file.')
        try:
            await asyncio.to_thread(self._image_preparer.check, path)
        except image_preparer_module.ImageError as error:
            return tool.ToolResult.error(f'{arguments.path}: {error}.')
        image = await asyncio.to_thread(self._image_preparer.prepare, path)
        if image is None:
            return tool.ToolResult.error(f'{arguments.path} could not be read.')
        return tool.ToolResult(
            text=f'This is the picture {arguments.path}.',
            image=image,
            picture_trader_path=self._trader_path(path),
        )

    def _trader_path(self, path: Path) -> str | None:
        """The picture's path relative to the trader folder, for the web page.

        Args:
            path (Path): The resolved picture path.

        Returns:
            str | None: The relative path, or None when the picture is outside the trader folder.
        """
        if not path.is_relative_to(self._policy.trader_directory):
            return None
        return path.relative_to(self._policy.trader_directory).as_posix()
