"""The browser_type tool: types into a numbered field from the latest snapshot.

Typical usage example:

  tool = BrowserTypeTool(session)
"""

import pydantic

from trading_agent.tools import browser_tool
from trading_agent.tools import tool


class BrowserTypeArguments(pydantic.BaseModel):
    """The arguments of browser_type.

    Attributes:
        element: The field's number from the latest snapshot.
        text: What to type; it replaces what the field holds.
        submit: Whether to press Enter afterwards, for example to run a search.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    element: int = pydantic.Field(ge=1)
    text: str
    submit: bool = False


class BrowserTypeTool(browser_tool.BrowserTool):
    """Types into a field."""

    name = 'browser_type'
    description = 'Types text into a numbered field from the latest browser snapshot, replacing what it holds, optionally pressing Enter, and returns the snapshot afterwards. Never type passwords or account details: this browser has no logins and must not be given any.'
    arguments_model = BrowserTypeArguments

    async def run(self, arguments: BrowserTypeArguments) -> tool.ToolResult:
        """Types the text.

        Args:
            arguments (BrowserTypeArguments): The field, the text and whether to submit.

        Returns:
            tool.ToolResult: The new snapshot, or an error.
        """
        return await self._text_result(
            self._session.type_text(
                arguments.element,
                arguments.text,
                arguments.submit,
            )
        )
