"""The browser_click tool: clicks a numbered element from the latest snapshot.

Typical usage example:

  tool = BrowserClickTool(session)
"""

import pydantic

from trading_agent.tools import browser_tool
from trading_agent.tools import tool


class BrowserClickArguments(pydantic.BaseModel):
    """The arguments of browser_click.

    Attributes:
        element: The element's number from the latest snapshot.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    element: int = pydantic.Field(ge=1)


class BrowserClickTool(browser_tool.BrowserTool):
    """Clicks an element."""

    name = 'browser_click'
    description = 'Clicks a numbered element from the latest browser snapshot and returns the snapshot after the click.'
    arguments_model = BrowserClickArguments

    async def run(self, arguments: BrowserClickArguments) -> tool.ToolResult:
        """Clicks the element.

        Args:
            arguments (BrowserClickArguments): The element's number.

        Returns:
            tool.ToolResult: The new snapshot, or an error.
        """
        return await self._text_result(self._session.click(arguments.element))
