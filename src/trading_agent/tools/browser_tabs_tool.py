"""The browser_tabs tool: lists, switches between and closes tabs.

Typical usage example:

  tool = BrowserTabsTool(session)
"""

from typing import Literal

import pydantic

from trading_agent.tools import browser_tool
from trading_agent.tools import tool


class BrowserTabsArguments(pydantic.BaseModel):
    """The arguments of browser_tabs.

    Attributes:
        action: "list" to see the tabs, "switch" to make one current, "close" to close one.
        tab: The tab's number from the list, for "switch" and "close".
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    action: Literal['list', 'switch', 'close'] = 'list'
    tab: int | None = pydantic.Field(default=None, ge=1)


class BrowserTabsTool(browser_tool.BrowserTool):
    """Manages tabs."""

    name = 'browser_tabs'
    description = 'Lists the open browser tabs, or switches to or closes one by its number. Links that open a new tab add to this list.'
    arguments_model = BrowserTabsArguments

    async def run(self, arguments: BrowserTabsArguments) -> tool.ToolResult:
        """Runs the tab action.

        Args:
            arguments (BrowserTabsArguments): The action and tab number.

        Returns:
            tool.ToolResult: The tabs after the action, or an error.
        """
        return await self._text_result(
            self._session.tabs(arguments.action, arguments.tab)
        )
