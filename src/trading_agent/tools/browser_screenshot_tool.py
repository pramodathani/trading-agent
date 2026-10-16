"""The browser_screenshot tool: shows the model a picture of the current page.

Typical usage example:

  tool = BrowserScreenshotTool(session, desk_directory)
"""

from pathlib import Path

from trading_agent.tools import browser_session as browser_session_module
from trading_agent.tools import browser_tool
from trading_agent.tools import tool


class BrowserScreenshotTool(browser_tool.BrowserTool):
    """Takes a screenshot of the visible part of the page."""

    name = 'browser_screenshot'
    description = 'Takes a screenshot of the visible part of the current page and shows it to you, for example to read a chart. Models that cannot see pictures should use browser_snapshot instead.'

    def __init__(
        self,
        session: browser_session_module.BrowserSession,
        desk_directory: Path,
    ):
        """Creates the tool.

        Args:
            session (browser_session_module.BrowserSession): The desk's browser.
            desk_directory (Path): The desk's folder, so the saved path can be shown relative to it.
        """
        super().__init__(session)
        self._desk_directory = desk_directory.resolve()

    async def run(self, arguments: tool.NoArguments) -> tool.ToolResult:
        """Takes the screenshot.

        Args:
            arguments (tool.NoArguments): No arguments.

        Returns:
            tool.ToolResult: Where the picture was saved, with the picture attached, or an error.
        """
        del arguments
        try:
            picture, path = await self._session.screenshot()
        except browser_session_module.BrowserError as error:
            return tool.ToolResult.error(str(error))
        shown_path = path.resolve().relative_to(self._desk_directory)
        return tool.ToolResult(
            text=f'Screenshot of the current page, saved as {shown_path}.',
            image_png=picture,
        )
